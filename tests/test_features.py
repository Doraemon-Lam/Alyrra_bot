import asyncio
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from features import Features, Store


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'test.sqlite3'
        self.store = Store(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def test_checkin_is_atomic_and_group_scoped(self):
        day = date(2026, 10, 12)
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.store.checkin('a', 'u', day), range(4)))
        self.assertEqual(sum(row[0] for row in results), 1)
        self.assertEqual(Store(self.path).profile('a', 'u')[0], 10)
        self.assertEqual(self.store.checkin('a', 'u', day + timedelta(days=1))[2], 2)
        self.assertEqual(self.store.checkin('a', 'u', day + timedelta(days=3))[2], 1)
        self.assertTrue(self.store.checkin('b', 'u', day)[0])

    def test_quota_flags_history_and_clear(self):
        for _ in range(5):
            self.assertTrue(self.store.reserve('a', 'u', 'fortune', 5))
        self.assertFalse(self.store.reserve('a', 'u', 'fortune', 5))
        self.store.set_enabled('a', 'fortune', False)
        self.assertFalse(Store(self.path).enabled('a', 'fortune'))
        self.assertTrue(self.store.enabled('b', 'fortune'))
        self.store.record('a', '1', 'u', 'name', 'hello')
        self.store.record('a', '1', 'u', 'name', 'updated')
        self.store.record('b', '2', 'v', 'other', 'private')
        self.assertEqual(self.store.recent('a', 30), [('u', 'name', 'updated')])
        self.store.clear('a')
        self.assertEqual(self.store.recent('a', 30), [])
        self.assertEqual(len(self.store.recent('b', 30)), 1)


class FeatureTests(unittest.IsolatedAsyncioTestCase):
    async def test_fortune_is_new_model_call_and_admin_is_required(self):
        with tempfile.TemporaryDirectory() as td:
            model = AsyncMock(return_value=SimpleNamespace(text='new fortune', usage_metadata=SimpleNamespace(total_token_count=100)))
            chat = SimpleNamespace(settings={'admin_member_openids': ['admin'], 'cards_enabled': False}, mode=lambda: 'active',
                lock=asyncio.Lock(), reserve=lambda direct: True, reload_settings=lambda: None,
                usage={'tokens': 24000}, save=lambda: None,
                bot=SimpleNamespace(vertex=SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=model)))))
            features = Features(chat, Path(td) / 'test.sqlite3')
            msg = SimpleNamespace(group_openid='g', author=SimpleNamespace(member_openid='u'), reply=AsyncMock())
            await features.handle(msg, '/幸运签')
            await features.handle(msg, '/幸运签')
            self.assertEqual(model.await_count, 2)
            prompts = [call.kwargs['contents'] for call in model.await_args_list]
            self.assertNotEqual(prompts[0], prompts[1])
            await features.handle(msg, '/功能 幸运签 关闭')
            self.assertTrue(features.store.enabled('g', 'fortune'))
            msg.author.member_openid = 'admin'
            await features.handle(msg, '/功能 幸运签 关闭')
            self.assertFalse(features.store.enabled('g', 'fortune'))
            self.assertNotIn('/幸运签', features.help('g'))


if __name__ == '__main__':
    unittest.main()
