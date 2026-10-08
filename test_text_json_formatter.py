"""仅用模型响应替身验证，不发送资料或调用真实 API。"""

from copy import deepcopy
import json
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from text_json_formatter import (
    FormatError, FORMAT_NOTICE, MAX_FORMAT_TEXT, format_corrected_text,
    read_json, validate_draft, validate_format_request,
)
from private_case_runner import validate_private_case, analyse_private_case


def payload(kind='combined'):
    return {'segments':[{'location':'第 1 行','text':'模拟岗位要求 Python 项目'},
                        {'location':'第 2 行','text':'虚构 Python 学习记录'}],
            'additional_text':'','text_kind':kind,'data_kind':'synthetic_private_test',
            'case_id':'formatted_draft','consent':True,'review_confirmed':True}


def proposal():
    return {'job':{'title':'待人工确认岗位','requirements':[{
        'skill_id':'python','description':'模拟岗位要求 Python 项目','category':'required','priority':2}]},
        'candidate':{'evidence':[{'skill_id':'python','description':'虚构 Python 学习记录','level':'learning'}]},
        'qualifications':[]}


def stub_client(value=None, *, finish='stop', refusal=None, tool_calls=None):
    client = MagicMock()
    client.with_options.return_value = client
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(finish_reason=finish,message=SimpleNamespace(
            content=json.dumps(value or proposal(),ensure_ascii=False),refusal=refusal,tool_calls=tool_calls))],
        usage=SimpleNamespace(prompt_tokens=120,completion_tokens=80))
    return client


class FormatterTests(unittest.TestCase):
    def test_complete_draft_uses_existing_contract_and_all_false(self):
        client = stub_client()
        original = payload()
        result = format_corrected_text(original,client_factory=lambda:client)
        draft = result['draft']
        validate_private_case(draft)
        self.assertTrue(result['schema_valid'])
        self.assertEqual(result['missing_sections'],[])
        self.assertEqual(draft['notice'],FORMAT_NOTICE)
        self.assertFalse(draft['candidate']['evidence'][0]['verified'])
        self.assertEqual(analyse_private_case(draft)['matches'][0]['status'],'unverified')
        self.assertEqual(original,payload())
        self.assertNotIn('expected',draft)
        self.assertNotIn('trusted_facts',draft)
        client.close.assert_called_once()

    def test_only_current_corrected_text_sent_and_request_is_bounded(self):
        value = payload()
        value['segments'][1]['text']='人工修改后的 Python 练习'
        output = proposal();output['candidate']['evidence'][0]['description']=value['segments'][1]['text']
        client = stub_client(output)
        format_corrected_text(value,client_factory=lambda:client)
        arguments = client.chat.completions.create.call_args.kwargs
        message = json.loads(arguments['messages'][1]['content'])
        self.assertEqual(message['corrected_segments'][1]['text'],'人工修改后的 Python 练习')
        self.assertNotIn('虚构 Python 学习记录',arguments['messages'][1]['content'])
        self.assertEqual(arguments['response_format'],{'type':'json_object'})
        self.assertNotIn('tools',arguments)
        self.assertEqual(arguments['max_completion_tokens'],4096)
        self.assertEqual(arguments['extra_body'],{'enable_thinking':False})
        client.with_options.assert_called_once_with(timeout=20.0,max_retries=0)

    def test_resume_only_does_not_invent_job(self):
        value = payload('resume');output=proposal();output['job']=None
        result = format_corrected_text(value,client_factory=lambda:stub_client(output))
        self.assertIsNone(result['draft']['job'])
        self.assertEqual(result['missing_sections'],['job'])
        self.assertFalse(result['schema_valid'])
        with self.assertRaises(FormatError):
            format_corrected_text(value,client_factory=lambda:stub_client())

    def test_jd_only_does_not_invent_candidate(self):
        value = payload('jd');output=proposal();output['candidate']=None
        result = format_corrected_text(value,client_factory=lambda:stub_client(output))
        self.assertIsNone(result['draft']['candidate'])
        self.assertEqual(result['missing_sections'],['candidate'])
        with self.assertRaises(FormatError):
            format_corrected_text(value,client_factory=lambda:stub_client())

    def test_supplement_quotes_must_come_from_correct_role(self):
        value = payload('resume');value['additional_text']='模拟岗位要求 Python 项目'
        result = format_corrected_text(value,client_factory=lambda:stub_client())
        self.assertTrue(result['schema_valid'])
        output=proposal();output['job']['requirements'][0]['description']='虚构 Python 学习记录'
        with self.assertRaises(FormatError):
            format_corrected_text(value,client_factory=lambda:stub_client(output))

    def test_missing_consent_or_review_no_client_created(self):
        for key in ['consent','review_confirmed']:
            for bad in [False,1,'true',None]:
                value=payload();value[key]=bad
                factory=MagicMock()
                with self.assertRaises(FormatError):
                    format_corrected_text(value,client_factory=factory)
                factory.assert_not_called()

    def test_sensitive_inputs_rejected_before_outbound(self):
        value=payload();value['additional_text']='demo-private@example.com'
        factory=MagicMock()
        with self.assertRaises(FormatError) as caught:
            format_corrected_text(value,client_factory=factory)
        self.assertEqual(caught.exception.code,'privacy')
        self.assertNotIn('example.com',str(caught.exception))
        factory.assert_not_called()

    def test_wrong_types_extra_config_and_text_limits_rejected(self):
        for key,bad in [('model','other'),('output_file','private'),('case_id','姓名'),('segments',[]),
                        ('additional_text','x'*(MAX_FORMAT_TEXT+1))]:
            value=payload();value[key]=bad
            with self.assertRaises(FormatError):
                validate_format_request(value)
        value=payload();value['segments'][0]['text']='x'*MAX_FORMAT_TEXT
        with self.assertRaises(FormatError):
            validate_format_request(value)

    def test_model_cannot_inject_verified_status_or_expected(self):
        for target,key,bad in [('evidence','verified',True),('root','expected',{}),('root','trusted_facts',[]),('requirement','status','matched')]:
            output=proposal()
            place=output['candidate']['evidence'][0] if target=='evidence' else output['job']['requirements'][0] if target=='requirement' else output
            place[key]=bad
            with self.assertRaises(FormatError):
                format_corrected_text(payload(),client_factory=lambda:stub_client(output))

    def test_model_quote_not_in_corrected_input_rejected(self):
        output=proposal();output['candidate']['evidence'][0]['description']='独立部署 Java 生产系统'
        with self.assertRaises(FormatError) as caught:
            format_corrected_text(payload(),client_factory=lambda:stub_client(output))
        self.assertEqual(caught.exception.code,'quote')
        self.assertNotIn('独立部署',str(caught.exception))

    def test_local_json_privacy_and_field_errors_are_distinct_and_fixed(self):
        draft=format_corrected_text(payload(),client_factory=lambda:stub_client())['draft']
        for change,code in [(lambda value:value.update(notice='demo-private@example.com'),'privacy'),
                            (lambda value:value['candidate']['evidence'][0].update(verified=True),'json')]:
            value=deepcopy(draft);change(value)
            with patch('text_json_formatter.create_qwen_client') as factory:
                with self.assertRaises(FormatError) as caught:
                    validate_draft(value)
                self.assertEqual(caught.exception.code,code)
                self.assertNotIn('example.com',str(caught.exception))
            factory.assert_not_called()

    def test_invalid_priority_levels_and_sensitive_output_rejected(self):
        for field,bad in [('priority',True),('priority','2'),('priority',4),('category',[]),('description','demo-private@example.com')]:
            output=proposal();output['job']['requirements'][0][field]=bad
            with self.assertRaises(FormatError):
                format_corrected_text(payload(),client_factory=lambda:stub_client(output))
        output=proposal();output['candidate']['evidence'][0]['level']='expert'
        with self.assertRaises(FormatError):
            format_corrected_text(payload(),client_factory=lambda:stub_client(output))

    def test_refusal_tool_request_or_truncated_result_rejected(self):
        for extra in [dict(finish='length'),dict(refusal='private-text'),dict(tool_calls=[{}])]:
            with self.assertRaises(FormatError):
                format_corrected_text(payload(),client_factory=lambda:stub_client(**extra))

    def test_malformed_duplicate_constant_or_deep_json_rejected(self):
        for text in ['{broken','{"job":null,"job":null}','{"x":NaN}','{"x":1e400}','{"x":'+'['*40+'0'+']'*40+'}']:
            with self.assertRaises(FormatError):
                read_json(text)

    def test_network_missing_key_and_bad_response_safe(self):
        factory=MagicMock(side_effect=RuntimeError('private-key-value'))
        with self.assertRaises(FormatError) as caught:
            format_corrected_text(payload(),client_factory=factory)
        self.assertEqual(caught.exception.code,'model')
        self.assertNotIn('private-key',str(caught.exception))
        client=stub_client();client.chat.completions.create.side_effect=RuntimeError('private-request')
        with self.assertRaises(FormatError):
            format_corrected_text(payload(),client_factory=lambda:client)
        client.close.assert_called_once()

    def test_user_json_revalidation_is_offline_and_cannot_upgrade(self):
        draft=format_corrected_text(payload(),client_factory=lambda:stub_client())['draft']
        with patch('text_json_formatter.create_qwen_client') as factory:
            result=validate_draft(draft)
            self.assertTrue(result['schema_valid'])
            draft['candidate']['evidence'][0]['verified']=True
            with self.assertRaises(FormatError):
                validate_draft(draft)
        factory.assert_not_called()

    def test_invalid_or_extra_draft_fields_rejected(self):
        draft=format_corrected_text(payload(),client_factory=lambda:stub_client())['draft']
        for key,bad in [('expected',{}),('case_id',[]),('data_kind',{}),('qualifications',[]),('notice','\x1b')]:
            value=deepcopy(draft);value[key]=bad
            if key=='qualifications':value[key]=[{'verification':'verified'}]
            with self.assertRaises(FormatError):
                validate_draft(value)

    def test_qualifications_stay_separate_and_unverified(self):
        value=payload();value['additional_text']='要求 2027 届硕士；声明 2027 届硕士'
        output=proposal();output['qualifications']=[{'required':'要求 2027 届硕士','declared':'声明 2027 届硕士'}]
        result=format_corrected_text(value,client_factory=lambda:stub_client(output))
        self.assertEqual(result['draft']['qualifications'][0]['verification'],'unverified')
        self.assertEqual(len(result['draft']['job']['requirements']),1)

    def test_sdk_timeout_is_safe_and_not_retried(self):
        from openai import APITimeoutError
        client=stub_client()
        client.chat.completions.create.side_effect=APITimeoutError(request=MagicMock())
        with self.assertRaises(FormatError) as caught:
            format_corrected_text(payload(),client_factory=lambda:client)
        self.assertEqual(caught.exception.code,'timeout')
        client.chat.completions.create.assert_called_once()
        client.close.assert_called_once()

    def test_quote_presence_does_not_prove_semantic_skill_mapping(self):
        value=payload();value['segments'][1]['text']='虚构数据库课程学习'
        output=proposal();output['candidate']['evidence'][0].update(
            {'skill_id':'mysql','description':'虚构数据库课程学习'})
        result=format_corrected_text(value,client_factory=lambda:stub_client(output))
        # 结构及摘录检查不能证明技能归类正确；仍为false，不能成为核验事实。
        self.assertFalse(result['draft']['candidate']['evidence'][0]['verified'])
        report=analyse_private_case(result['draft'])
        self.assertEqual(report['matches'][0]['status'],'missing')
        self.assertEqual(report['trusted_facts'][0]['verified_evidence_ids'],[])


if __name__=='__main__':
    unittest.main()
