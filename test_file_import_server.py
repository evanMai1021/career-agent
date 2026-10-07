"""本机导入接口测试；只有虚构字节，不依赖真实资料或监听端口。"""

import asyncio
from contextlib import redirect_stderr
import io
import json
import unittest
from unittest.mock import patch

import httpx

from fastapi.testclient import TestClient
from fastapi import HTTPException
from file_import_server import create_import_app, main, _read_upload
from file_importer import MAX_FILE_BYTES, FileImportError
from test_file_importer import docx_bytes, pdf_bytes
from test_text_json_formatter import payload as format_payload,stub_client

HEADERS = {'X-CareerAgent-Import':'local-preview', 'X-File-Format':'txt', 'Content-Type':'application/octet-stream'}


class ImportServerTests(unittest.TestCase):
    def setUp(self):
        self.app = create_import_app()
        self.client = TestClient(self.app, base_url='http://127.0.0.1:8002',client=('127.0.0.1',50000))

    def test_page_is_empty_and_has_no_external_dependencies(self):
        response = self.client.get('/import')
        self.assertEqual(response.status_code,200)
        self.assertIn('type="file"',response.text)
        self.assertNotIn('innerHTML',response.text)
        self.assertNotIn('<script src=',response.text)
        self.assertNotIn('localStorage',response.text)
        self.assertIsNone(self.app.openapi_url)

    def test_actual_api_three_formats_and_no_persistence(self):
        for kind, content in [('txt','纯虚构测试'.encode()),('pdf',pdf_bytes()),('docx',docx_bytes())]:
            with self.subTest(kind=kind):
                response = self.client.post('/imports/text',content=content,headers={**HEADERS,'X-File-Format':kind})
                self.assertEqual(response.status_code,200,response.text)
                self.assertFalse(response.json()['saved'])
                self.assertFalse(response.json()['analysis_performed'])
                self.assertEqual(response.json()['verification'],'unverified')
        self.assertEqual(self.client.get('/imports/text',headers=HEADERS).status_code,405)
        self.assertEqual(self.client.get('/private/case').status_code,404)
        self.assertEqual(self.client.post('/analyses',json={}).status_code,404)

    def test_bad_format_content_type_and_no_parser(self):
        with patch('file_import_server.extract_document') as parser:
            for extra in [{'X-File-Format':'doc'}, {'X-File-Format':'exe'}, {'Content-Type':'multipart/form-data'}]:
                self.assertEqual(self.client.post('/imports/text',headers={**HEADERS,**extra},content=b'fiction').status_code,415)
        parser.assert_not_called()

    def test_custom_header_required_before_parsing(self):
        with patch('file_import_server.extract_document') as parser:
            self.assertEqual(self.client.post('/imports/text',content=b'fiction').status_code,403)
        parser.assert_not_called()

    def test_host_origin_remote_client_and_proxy_rejected(self):
        for extra in [{'Host':'localhost:8002'},{'Origin':'https://evil.example'},
                      {'Sec-Fetch-Site':'cross-site'},{'X-Forwarded-For':'127.0.0.1'},
                      {'Forwarded':'fiction'},{'X-Forwarded-Host':'fiction'}]:
            self.assertEqual(self.client.post('/imports/text',content=b'fiction',headers={**HEADERS,**extra}).status_code,403)
        remote = TestClient(self.app,base_url='http://127.0.0.1:8002',client=('192.0.2.1',50000))
        self.assertEqual(remote.get('/import').status_code,403)
        self.assertEqual(self.client.options('/imports/text',headers={'Origin':'https://evil.example'}).status_code,403)

    def test_query_paths_are_rejected_before_parser(self):
        with patch('file_import_server.extract_document') as parser:
            response = self.client.post('/imports/text?path=private-value',headers=HEADERS,content=b'fiction')
            self.assertEqual(response.status_code,422)
            self.assertNotIn('private-value',response.text)
        parser.assert_not_called()

    def test_size_and_invalid_length(self):
        for value, expected in [('99999999999999999999',413),('nonsense',422),('-1',422)]:
            response = self.client.post('/imports/text',headers={**HEADERS,'Content-Length':value},content=b'fiction')
            self.assertEqual(response.status_code,expected)
        self.assertEqual(self.client.post('/imports/text',headers=HEADERS,content=b'').status_code,413)

    def test_chunked_body_without_length_and_limit(self):
        class Request:
            async def stream(self):
                yield b'x'*MAX_FILE_BYTES
                yield b'x'
        with self.assertRaises(HTTPException) as caught:
            asyncio.run(_read_upload(Request()))
        self.assertEqual(caught.exception.status_code,413)
        response = self.client.post('/imports/text',headers=HEADERS,content=iter([b'fiction ',b'text']))
        self.assertEqual(response.status_code,200)

    def test_safe_errors_and_retry(self):
        for code,status in [('invalid',422),('empty',422),('timeout',408),('resource',503),('limit',413)]:
            with patch('file_import_server.extract_document',side_effect=FileImportError(code)):
                response = self.client.post('/imports/text',headers=HEADERS,content=b'fiction')
                self.assertEqual(response.status_code,status)
        self.assertEqual(self.client.post('/imports/text',headers=HEADERS,content=b'fiction').status_code,200)

    def test_upload_timeout_has_fixed_message(self):
        with patch('file_import_server._read_upload',side_effect=TimeoutError('private-value')):
            response = self.client.post('/imports/text',headers=HEADERS,content=b'fiction')
            self.assertEqual(response.status_code,408)
            self.assertNotIn('private-value',response.text)

    def test_concurrent_import_rejected_and_lock_released(self):
        async def scenario():
            started,released = asyncio.Event(),asyncio.Event()
            async def read(request):
                started.set()
                await released.wait()
                return b'fiction'
            transport = httpx.ASGITransport(app=self.app,client=('127.0.0.1',50000))
            async with httpx.AsyncClient(transport=transport,base_url='http://127.0.0.1:8002') as client:
                with patch('file_import_server._read_upload',side_effect=read):
                    first = asyncio.create_task(client.post('/imports/text',headers=HEADERS,content=b'fiction'))
                    await started.wait()
                    second = await client.post('/imports/text',headers=HEADERS,content=b'fiction')
                    self.assertEqual(second.status_code,503)
                    released.set()
                    self.assertEqual((await first).status_code,200)
                self.assertEqual((await client.post('/imports/text',headers=HEADERS,content=b'fiction')).status_code,200)
        asyncio.run(scenario())

    def test_cache_headers_and_page_missing(self):
        with patch('file_import_server.PAGE_FILE') as page:
            page.read_text.side_effect = OSError('private-path')
            response = self.client.get('/import')
            self.assertEqual(response.status_code,503)
            self.assertNotIn('private-path',response.text)
        for response in [self.client.get('/import'),self.client.post('/imports/text',content=b'fiction')]:
            self.assertEqual(response.headers['cache-control'],'no-store')
            self.assertEqual(response.headers['x-frame-options'],'DENY')

    def test_launcher_is_local_no_logs_and_invalid_args_safe(self):
        with patch('file_import_server.uvicorn.run') as run:
            self.assertEqual(main(['--port','8092']),0)
            self.assertEqual(run.call_args.kwargs['host'],'127.0.0.1')
            self.assertFalse(run.call_args.kwargs['access_log'])
            self.assertFalse(run.call_args.kwargs['proxy_headers'])
        output = io.StringIO()
        with redirect_stderr(output):
            self.assertEqual(main(['--port','private-value']),2)
        self.assertNotIn('private-value',output.getvalue())

    def test_model_disabled_by_default_and_header_required(self):
        with patch('text_json_formatter.create_qwen_client') as factory:
            response=self.client.post('/imports/format-json',headers={**HEADERS,'Content-Type':'application/json'},json=format_payload())
            self.assertEqual(response.status_code,403)
            self.assertIn('const MODEL_ENABLED=false;',self.client.get('/import').text)
            enabled=TestClient(create_import_app(enable_model_format=True),base_url='http://127.0.0.1:8002',client=('127.0.0.1',50000))
            self.assertIn('const MODEL_ENABLED=true;',enabled.get('/import').text)
            self.assertEqual(enabled.post('/imports/format-json',json=format_payload()).status_code,403)
        factory.assert_not_called()

    def test_enabled_formatter_uses_corrected_payload_with_stub_only(self):
        enabled=TestClient(create_import_app(enable_model_format=True),base_url='http://127.0.0.1:8002',client=('127.0.0.1',50000))
        with patch('text_json_formatter.create_qwen_client',return_value=stub_client()) as factory:
            response=enabled.post('/imports/format-json',headers={**HEADERS,'Content-Type':'application/json'},json=format_payload())
        self.assertEqual(response.status_code,200,response.text)
        self.assertTrue(response.json()['model_generated'])
        factory.assert_called_once()

    def test_consent_privacy_extra_fields_and_duplicate_json_rejected_without_model(self):
        enabled=TestClient(create_import_app(enable_model_format=True),base_url='http://127.0.0.1:8002',client=('127.0.0.1',50000))
        headers={**HEADERS,'Content-Type':'application/json'}
        with patch('text_json_formatter.create_qwen_client') as factory:
            for key,bad in [('consent',False),('review_confirmed',False),('model','other'),('additional_text','demo-private@example.com')]:
                value=format_payload();value[key]=bad
                response=enabled.post('/imports/format-json',headers=headers,json=value)
                self.assertEqual(response.status_code,422)
                self.assertNotIn('example.com',response.text)
            self.assertEqual(enabled.post('/imports/format-json',headers=headers,content=b'{"consent":true,"consent":true}').status_code,422)
            self.assertEqual(enabled.post('/imports/format-json?path=private-value',headers=headers,json=format_payload()).status_code,422)
        factory.assert_not_called()

    def test_validate_json_offline_and_false_flag_enforced(self):
        enabled=TestClient(create_import_app(enable_model_format=True),base_url='http://127.0.0.1:8002',client=('127.0.0.1',50000))
        headers={**HEADERS,'Content-Type':'application/json'}
        with patch('text_json_formatter.create_qwen_client',return_value=stub_client()):
            draft=enabled.post('/imports/format-json',headers=headers,json=format_payload()).json()['draft']
        with patch('text_json_formatter.create_qwen_client') as factory:
            result=self.client.post('/imports/validate-json',headers=headers,json={'draft':draft})
            self.assertEqual(result.status_code,200)
            self.assertTrue(result.json()['schema_valid'])
            draft['candidate']['evidence'][0]['verified']=True
            self.assertEqual(self.client.post('/imports/validate-json',headers=headers,json={'draft':draft}).status_code,422)
            self.assertEqual(self.client.post('/imports/validate-json',headers=headers,json={'draft':{},'output_file':'private'}).status_code,422)
        factory.assert_not_called()

    def test_formatter_errors_are_fixed_and_headers_preserved(self):
        from text_json_formatter import FormatError
        enabled=TestClient(create_import_app(enable_model_format=True),base_url='http://127.0.0.1:8002',client=('127.0.0.1',50000))
        for code,status in [('model',503),('output',422),('timeout',408)]:
            with patch('file_import_server.format_corrected_text',side_effect=FormatError(code)):
                response=enabled.post('/imports/format-json',headers={**HEADERS,'Content-Type':'application/json'},json=format_payload())
                self.assertEqual(response.status_code,status)
                self.assertEqual(response.headers['cache-control'],'no-store')

    def test_raw_edited_json_rejects_duplicate_keys_and_nonfinite_numbers(self):
        from text_json_formatter import format_corrected_text
        draft=format_corrected_text(format_payload(),client_factory=lambda:stub_client())['draft']
        raw=json.dumps(draft,ensure_ascii=False)
        invalid=[raw.replace('{','{"case_id":"other_draft",',1),
                 raw.replace('"verified": false','"verified": true, "verified": false'),
                 raw.replace('"priority": 2','"priority": 1e400')]
        headers={**HEADERS,'Content-Type':'application/json'}
        with patch('text_json_formatter.create_qwen_client') as factory:
            self.assertEqual(self.client.post('/imports/validate-json',headers=headers,
                content=('{"draft":'+raw+'}').encode('utf-8')).status_code,200)
            for text in invalid:
                response=self.client.post('/imports/validate-json',headers=headers,
                    content=('{"draft":'+text+'}').encode('utf-8'))
                self.assertEqual(response.status_code,422)
                self.assertEqual(response.headers['cache-control'],'no-store')
        factory.assert_not_called()

    def test_model_launch_flag_only_enables_route_not_request(self):
        with patch('file_import_server.uvicorn.run') as run,patch('text_json_formatter.create_qwen_client') as factory:
            self.assertEqual(main(['--enable-model-format']),0)
            self.assertIn('const MODEL_ENABLED=true;',TestClient(run.call_args.args[0],base_url='http://127.0.0.1:8002',client=('127.0.0.1',50000)).get('/import').text)
        factory.assert_not_called()


if __name__ == '__main__':
    unittest.main()
