import base64
import io
import json
import threading
import unittest
from unittest.mock import patch
import server
from sessions import Sessions

class EphemeralTests(unittest.TestCase):
    def test_each_tab_has_isolated_sources_and_messages(self):
        pool=Sessions(server.Discussion)
        a,b=pool.open(),pool.open()
        pool.get(a).sources['private']={'raw':b'secret'}
        pool.get(a).state['messages'].append({'text':'confidentiel'})
        self.assertEqual(pool.get(b).sources,{})
        self.assertEqual(pool.get(b).state['messages'],[])
        pool.end(a)
        self.assertIsNone(pool.get(a))
        self.assertIsNotNone(pool.get(b))

    def test_end_clears_sources_outputs_messages_and_sets_cancellation(self):
        pool=Sessions(server.Discussion)
        key=pool.open();d=pool.get(key)
        d.sources['x']={'raw':b'private'};d.active_sources=[{'raw':b'private'}]
        d.generated['y']={'raw':b'private'}
        d.state['messages'].append({'text':'private'})
        pool.end(key);pool.end(key)
        self.assertTrue(d.stop_event.is_set())
        self.assertEqual((d.sources,d.generated,d.active_sources,d.snapshot()['messages']),({},{},[],[]))
        d.update(status='late result')
        self.assertEqual(d.snapshot()['status'],'Discussion effacée')
        with self.assertRaises(InterruptedError):d.append_result('Codex','late','secret',[])

    def test_expiration_without_browser_close_notification(self):
        now=[10]
        pool=Sessions(server.Discussion,ttl=120,clock=lambda:now[0])
        key=pool.open();d=pool.get(key)
        now[0]=130;pool.expire()
        self.assertIsNone(pool.get(key));self.assertTrue(d.closed)

    def test_upload_finishing_after_close_cannot_restore_data(self):
        d=server.Discussion()
        def finish(*args):
            d.dispose()
            return {'text':'secret','warnings':[],'sha256':'x'}
        with patch.object(server,'extract',side_effect=finish):
            with self.assertRaises(ValueError):
                d.upload({'name':'note.txt','content':base64.b64encode(b'secret').decode()})
        self.assertEqual(d.sources,{})

    def test_closed_session_cannot_start_or_call_cli(self):
        d=server.Discussion();d.dispose()
        with self.assertRaises(ValueError):d.start('test',1,True)
        with patch.object(server.subprocess,'Popen') as launch:
            with self.assertRaises(InterruptedError):d.call('Codex','secret')
            launch.assert_not_called()

if __name__=='__main__':unittest.main()
