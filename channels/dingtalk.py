import asyncio
import json
import logging
import time
from urllib.parse import quote_plus, urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError

import dingtalk_stream
import websockets

from codex_bridge.router import InboundMessage


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def normalize(data):
    if not isinstance(data, dict) or data.get('msgtype') != 'text':
        return None
    fields = [data.get(k) for k in ('msgId','senderStaffId','conversationId')]
    text = data.get('text', {}).get('content') if isinstance(data.get('text'), dict) else None
    if not all(isinstance(x, str) and x for x in fields) or not isinstance(text, str):
        return None
    return InboundMessage('dingtalk', *fields, 'private' if str(data.get('conversationType')) == '1' else 'group', text)


def post(url, body, headers=None):
    # No token/body/URL is printed. urllib errors are translated at the boundary.
    request = Request(url, data=json.dumps(body).encode(), headers={'Content-Type':'application/json', **(headers or {})})
    try:
        with build_opener(NoRedirect()).open(request, timeout=20) as response:
            return json.loads(response.read(1024*1024))
    except (HTTPError, OSError, ValueError):
        raise RuntimeError('DingTalk request failed') from None


class DingTalk:
    def __init__(self, config, router):
        self.config, self.router = config, router
        self.tasks = set()
        self.stopping = False
        self.ws = None
        self.token = None
        self.token_expiry = 0
        self.token_lock = asyncio.Lock()
        self.client = dingtalk_stream.DingTalkStreamClient(
            dingtalk_stream.Credential(config.client_id, config.client_secret))
        logger = logging.getLogger('bridge.sdk.silent')
        logger.handlers = [logging.NullHandler()]
        logger.propagate = False
        logger.setLevel(logging.CRITICAL+1)
        self.client.logger = logger
        self.client.system_handler.logger = logger
        self.client.event_handler.logger = logger
        owner = self
        class Handler(dingtalk_stream.ChatbotHandler):
            async def process(self, callback):
                msg = normalize(callback.data)
                if msg and owner.router.authorized(msg) and len(owner.tasks) < 32 and not owner.stopping:
                    if msg.conversation_type == 'private':
                        async def send(text):
                            await owner.send_private(msg.sender_id, text)
                        task = asyncio.create_task(owner.router.handle(msg, send))
                        owner.tasks.add(task)
                        def completed(future):
                            owner.tasks.discard(future)
                            if not future.cancelled() and future.exception():
                                print('Channel request failed; inspect local configuration.', flush=True)
                        task.add_done_callback(completed)
                return dingtalk_stream.AckMessage.STATUS_OK, 'OK'
        handler = Handler()
        handler.logger = logger
        self.client.register_callback_handler(dingtalk_stream.ChatbotMessage.TOPIC, handler)

    async def send_private(self, sender, text):
        if sender not in self.config.users:
            raise RuntimeError('Recipient not authorized')
        async with self.token_lock:
            if not self.token or self.token_expiry <= time.monotonic():
                token = await asyncio.to_thread(post, 'https://api.dingtalk.com/v1.0/oauth2/accessToken',
                    {'appKey':self.config.client_id,'appSecret':self.config.client_secret})
                self.token = token.get('accessToken')
                if not isinstance(self.token, str) or not self.token:
                    raise RuntimeError('DingTalk token unavailable')
                self.token_expiry = time.monotonic() + max(0, min(int(token.get('expireIn', 0)),7200)-60)
            access_token = self.token
        result = await asyncio.to_thread(post, 'https://api.dingtalk.com/v1.0/robot/oToMessages/batchSend',
            {'robotCode':self.config.client_id,'userIds':[sender], 'msgKey':'sampleText',
             'msgParam':json.dumps({'content':text},ensure_ascii=False)},
            {'x-acs-dingtalk-access-token':access_token})
        if not result.get('processQueryKey') or result.get('invalidStaffIdList') or result.get('flowControlledStaffIdList'):
            raise RuntimeError('DingTalk delivery not confirmed')

    async def run(self):
        self.client.pre_start()
        delay = 1
        while not self.stopping:
            try:
                conn = await asyncio.to_thread(post, self.client.OPEN_CONNECTION_API, {
                    'clientId':self.config.client_id,'clientSecret':self.config.client_secret,
                    'subscriptions':[{'type':'CALLBACK','topic':dingtalk_stream.ChatbotMessage.TOPIC}],
                    'ua':'codex-remote-bridge/0.1.0','localIp':''})
                endpoint = urlparse(conn.get('endpoint', ''))
                if endpoint.scheme != 'wss' or not (endpoint.hostname or '').endswith('.dingtalk.com'):
                    raise RuntimeError('Invalid Stream endpoint')
                async with websockets.connect(conn['endpoint']+'?ticket='+quote_plus(conn['ticket']),
                        open_timeout=20, ping_interval=20, ping_timeout=20, max_size=1024*1024) as ws:
                    self.ws = self.client.websocket = ws
                    delay = 1
                    print('DingTalk Stream connected.', flush=True)
                    async for raw in ws:
                        if self.stopping:
                            break
                        if await self.client.route_message(json.loads(raw)) == self.client.TAG_DISCONNECT:
                            break
            except asyncio.CancelledError:
                raise
            except Exception:
                print('DingTalk disconnected; retrying without replaying user commands.', flush=True)
            finally:
                self.ws = None
            if not self.stopping:
                await asyncio.sleep(delay)
                delay = min(delay*2, 30)

    async def close(self):
        self.stopping = True
        if self.ws:
            await self.ws.close()
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
