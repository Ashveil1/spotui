import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

spec = importlib.util.spec_from_file_location('player', Path(__file__).parents[1] / 'spotui.py')
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)


def track(i):
    return dict(id=str(i), title=f'Song {i}', artist='Artist', dur=120,
                url=f'https://www.youtube.com/watch?v={i}')


class AppTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for name, value in [('CFG', root), ('STORE', root / 'library.json')]:
            p = patch.object(s, name, value)
            p.start()
            self.addCleanup(p.stop)
        with patch.object(s.threading.Thread, 'start'):
            self.app = s.App()
        self.app.refresh_similar = Mock()

    def test_home_keyboard_navigation(self):
        self.app.create_playlist('Rock')
        self.app.back()
        s.handle_key(self.app, 'j')
        self.assertEqual(self.app.sel_row(), 1)
        s.handle_key(self.app, '\n')
        self.assertEqual(self.app.stack[-1], ('playlist', 0))

    def test_new_playlist_keeps_pending_song(self):
        t = track(1)
        self.app.open_pick(t)
        s.handle_key(self.app, '\n')
        for c in 'Rock':
            s.handle_key(self.app, c)
        s.handle_key(self.app, '\n')
        self.assertEqual(self.app.store.playlists[0]['tracks'][0]['id'], '1')
        self.assertIsNone(self.app.pick_pending)

    def test_queue_row_preserves_queue(self):
        self.app.queue = [track(i) for i in range(3)]
        self.app._play_current = Mock()
        self.app.play_row('queue:', 1)
        self.assertEqual(self.app.qpos, 1)
        self.assertEqual(len(self.app.queue), 3)
        self.app._play_current.assert_called_once()

    def test_delete_first_playing_row_advances_to_new_first(self):
        self.app.queue = [track(i) for i in range(3)]
        self.app.qpos = 0
        self.app.push('queue')
        self.app.delete_selected()
        self.assertEqual(self.app.qpos, -1)
        self.app._play_current = Mock()
        self.app.next(auto=True)
        self.assertEqual(self.app.queue[self.app.qpos]['id'], '1')

    def test_volume_persists_clamped_value(self):
        self.app.vol(absolute=400)
        self.assertEqual(self.app.store.volume, 100)
        self.app.vol(absolute=-30)
        self.assertEqual(self.app.store.volume, 0)

    def test_stale_resolver_does_not_replace_new_track(self):
        self.app.load_token = 2
        self.app.mpv.load = Mock()
        with patch.object(s, 'HAVE_YTDL', True), patch.object(s, 'resolve_url', return_value='audio'):
            self.app._resolve_load(track(1), 1)
        self.app.mpv.load.assert_not_called()

    def test_failed_play_not_recorded_in_history(self):
        self.app.mpv.load = Mock(return_value=False)
        with patch.object(s, 'HAVE_YTDL', True), patch.object(s, 'resolve_url', return_value='audio'):
            self.app._resolve_load(track(1))
        self.assertEqual(self.app.store.history, [])

    def test_successful_play_recorded(self):
        self.app.mpv.load = Mock(return_value=True)
        with patch.object(s, 'HAVE_YTDL', True), patch.object(s, 'resolve_url', return_value='audio'):
            self.app._resolve_load(track(1))
        self.assertEqual(self.app.store.history[0]['id'], '1')

    def test_thai_recommendations_not_discarded(self):
        items = [dict(track(1), title='เพลงรัก'), dict(track(2), title='ฝนตก')]
        self.assertEqual(len(self.app._pick_similar(items)), 2)

    def test_mouse_rect_bottom_is_exclusive(self):
        self.app.rects = [dict(x0=0, x1=5, y0=1, y1=2, act='toggle', arg=None)]
        self.app.toggle = Mock()
        with patch.object(s.curses, 'getmouse', return_value=(0, 2, 2, 0, s.curses.BUTTON1_CLICKED)):
            s.handle_mouse(self.app)
        self.app.toggle.assert_not_called()

    def test_mouse_works_without_button5_constant(self):
        self.app.rects = [dict(x0=0, x1=5, y0=1, y1=2, act='toggle', arg=None)]
        self.app.toggle = Mock()
        with patch.object(s.curses, 'BUTTON5_PRESSED', 0, create=True), patch.object(
                s.curses, 'getmouse', return_value=(0, 2, 1, 0, s.curses.BUTTON1_CLICKED)):
            s.handle_mouse(self.app)
        self.app.toggle.assert_called_once()

    def test_mouse_release_does_not_double_activate(self):
        self.app.rects = [dict(x0=0, x1=5, y0=1, y1=2, act='toggle', arg=None)]
        self.app.toggle = Mock()
        with patch.object(s.curses, 'getmouse', return_value=(0, 2, 1, 0, s.curses.BUTTON1_RELEASED)):
            s.handle_mouse(self.app)
        self.app.toggle.assert_not_called()

    def test_corrupt_library_is_never_overwritten(self):
        s.STORE.write_text('{broken', encoding='utf-8')
        store = s.Store()
        self.assertTrue(store.error)
        self.assertFalse(store.save())
        self.assertEqual(s.STORE.read_text(), '{broken')

    def test_malformed_library_fields_are_sanitized(self):
        s.STORE.write_text('{"liked":[null,{}, {"id":"../bad"}, {"id":"valid"}], "volume":"oops", "playlists":null, "recent":42}')
        store = s.Store()
        self.assertEqual([t['id'] for t in store.liked], ['valid'])
        self.assertEqual(store.liked[0]['title'], 'Unknown title')
        self.assertEqual(store.volume, 70)
        self.assertEqual(store.playlists, [])

    def test_concurrent_saves_keep_valid_json(self):
        import threading
        import json
        self.app.store.liked = [track(1)]
        results = []
        threads = [threading.Thread(target=lambda: results.append(self.app.store.save())) for _ in range(12)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertTrue(all(results))
        self.assertEqual(json.loads(s.STORE.read_text())['liked'][0]['id'], '1')
        self.assertEqual(list(s.CFG.iterdir()), [s.STORE])


class MpvTests(unittest.TestCase):
    def test_load_checks_command_success_not_null_data(self):
        mpv = s.Mpv()
        mpv.ensure = Mock(return_value=True)
        mpv.cmd = Mock(return_value=True)
        self.assertTrue(mpv.load('audio'))
        self.assertEqual(mpv.cmd.call_args_list[0].kwargs, {'status': True})

    def test_null_data_success_status_over_ipc(self):
        mpv = s.Mpv()
        mpv.alive = Mock(return_value=True)
        sock = Mock()
        sock.recv.return_value = b'{"request_id":1,"error":"success"}\n'
        with patch.object(s.socket, 'socket', return_value=sock):
            self.assertTrue(mpv.cmd(['loadfile', 'audio'], status=True))

    def test_error_status_over_ipc(self):
        mpv = s.Mpv()
        mpv.alive = Mock(return_value=True)
        sock = Mock()
        sock.recv.return_value = b'{"request_id":1,"error":"invalid parameter"}\n'
        with patch.object(s.socket, 'socket', return_value=sock):
            self.assertFalse(mpv.cmd(['loadfile', 'audio'], status=True))


if __name__ == '__main__':
    unittest.main()
