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

    def test_session_queue_restores_paused(self):
        self.app.queue = [track(1), track(2), track(3)]
        self.app.qpos = 1
        self.app.snapshot_session()
        self.assertTrue(self.app.store.save())
        with patch.object(s.threading.Thread, 'start'):
            app2 = s.App()
        self.assertEqual([t['id'] for t in app2.queue], ['1', '2', '3'])
        self.assertEqual(app2.qpos, 1)
        self.assertIsNone(app2.current)

    def test_session_bad_position_ignored(self):
        self.app.queue = [track(1)]
        self.app.qpos = 0
        self.app.snapshot_session()
        self.app.store.session['pos'] = 9
        self.app.store.save()
        with patch.object(s.threading.Thread, 'start'):
            app2 = s.App()
        self.assertEqual(app2.queue, [])

    def test_find_jumps_to_match(self):
        self.app.store.liked = [dict(track(1), title='Alpha'), dict(track(2), title='Beta'),
                                dict(track(3), title='Gamma', artist='Zed')]
        self.app.push('liked')
        s.handle_key(self.app, 'F')
        self.assertEqual(self.app.mode, 'find')
        for c in 'zed':
            s.handle_key(self.app, c)
        self.assertEqual(self.app.sel_row(), 2)
        s.handle_key(self.app, '\n')
        self.assertEqual(self.app.mode, 'normal')
        self.assertEqual(len(self.app.store.liked), 3)

    def test_save_queue_as_playlist_dedupes(self):
        self.app.queue = [track(1), track(2), track(1)]
        self.app.push('queue')
        s.handle_key(self.app, 'W')
        self.assertEqual(len(self.app.store.playlists), 1)
        self.assertEqual([x['id'] for x in self.app.store.playlists[0]['tracks']], ['1', '2'])

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

    def test_put_clips_by_terminal_cells(self):
        scr = Mock()
        scr.getmaxyx.return_value = (10, 8)
        with patch.object(s.curses, 'color_pair', return_value=0):
            s.put(scr, 0, 3, '中文abc', 0)
        self.assertEqual(scr.addstr.call_args.args[2], '中文')

    def test_put_drops_control_characters(self):
        scr = Mock()
        scr.getmaxyx.return_value = (10, 40)
        with patch.object(s.curses, 'color_pair', return_value=0):
            s.put(scr, 0, 0, 'song\nname\x1b', 0)
        self.assertEqual(scr.addstr.call_args.args[2], 'songname')

    def test_playlist_picker_scrolls_selected_item_into_view(self):
        self.app.pick_rows = [dict(name=str(i)) for i in range(25)]
        self.app.pick_idx = 24
        self.app.pal = {key: 0 for key in ['dim', 'side', 'hover', 'sdim']}
        scr = Mock()
        scr.getmaxyx.return_value = (40, 120)
        with patch.object(s.curses, 'color_pair', return_value=0):
            s.UI(self.app, scr).pick_modal(35, 120)
        rows = [r['arg'] for r in self.app.rects if r['act'] == 'pickrow']
        self.assertIn(24, rows)
        self.assertNotIn(0, rows)

    def test_queue_scrolls_selected_item_into_view(self):
        self.app.queue = [track(i) for i in range(40)]
        self.app.current = self.app.queue[0]
        self.app.qpos = 0
        self.app.sel['queue:'] = 35
        self.app.pal = dict(text=0, faint=0, dim=0)
        ui = s.UI(self.app, Mock())
        ui.row = Mock()
        with patch.object(s, 'put'):
            ui.v_queue(3, 25, 24, 120)
        indices = [c.args[6] for c in ui.row.call_args_list]
        self.assertIn(35, indices)

    def test_radio_does_not_overwrite_user_queue_edits(self):
        self.app.current = track(1)
        self.app.queue = [track(1)]
        rev = self.app.queue_revision
        self.app.add_queue(track(2))
        with patch.object(s, '_ytdl_playlist', return_value=[track(3)]):
            self.app._radio_worker(track(1), rev, self.app.load_token)
        self.assertEqual([t['id'] for t in self.app.queue], ['1', '2'])

    def test_empty_radio_preserves_search_queue(self):
        self.app.current = track(1)
        self.app.queue = [track(1), track(2)]
        with patch.object(s, '_ytdl_playlist', return_value=[]):
            self.app._radio_worker(track(1))
        self.assertEqual(len(self.app.queue), 2)

    def test_quit_cancels_resolver(self):
        self.app.quit = True
        self.app.mpv.load = Mock()
        with patch.object(s, 'HAVE_YTDL', True), patch.object(s, 'resolve_url', return_value='audio'):
            self.app._resolve_load(track(1))
        self.app.mpv.load.assert_not_called()

    def test_playlist_rename(self):
        self.app.create_playlist('Old')
        s.handle_key(self.app, 'e')
        self.app.name_buf = 'New'
        s.handle_key(self.app, s.curses.KEY_ENTER)
        self.assertEqual(self.app.store.playlists[0]['name'], 'New')

    def test_playlist_delete_requires_confirmation_and_reindexes(self):
        for name in ['One', 'Two', 'Three']:
            self.app.create_playlist(name)
        self.app.sel['playlist:2'] = 3
        self.app.push('playlist', 1)
        s.handle_key(self.app, 'D')
        self.assertEqual(len(self.app.store.playlists), 3)
        s.handle_key(self.app, 'n')
        self.assertEqual(len(self.app.store.playlists), 3)
        s.handle_key(self.app, 'D')
        s.handle_key(self.app, 'y')
        self.assertEqual([p['name'] for p in self.app.store.playlists], ['One', 'Three'])
        self.assertEqual(self.app.sel['playlist:1'], 3)
        self.assertNotIn(('playlist', 2), self.app.stack)

    def test_name_cancel_clears_pending_track(self):
        self.app.open_pick(track(1))
        s.handle_key(self.app, '\n')
        s.handle_key(self.app, '\x1b')
        self.assertIsNone(self.app.pick_pending)

    def test_shuffle_preserves_current_and_restores_order(self):
        self.app.queue = [dict(track(i), artist=str(i % 3)) for i in range(12)]
        original = list(self.app.queue)
        self.app.qpos = 2
        self.app.current = self.app.queue[2]
        self.app._apply_shuffle(True)
        self.assertEqual(self.app.queue[:3], original[:3])
        self.assertCountEqual(self.app.queue, original)
        self.app._apply_shuffle(False)
        self.assertEqual(self.app.queue, original)
        self.assertEqual(self.app.qpos, 2)

    def test_shuffle_deleted_song_not_resurrected(self):
        self.app.queue = [track(i) for i in range(6)]
        self.app.qpos = 0
        self.app.current = self.app.queue[0]
        self.app._apply_shuffle(True)
        removed = self.app.queue[3]['id']
        self.app.push('queue')
        self.app.sel['queue:'] = 3
        self.app.delete_selected()
        self.app._apply_shuffle(False)
        self.assertNotIn(removed, [t['id'] for t in self.app.queue])

    def test_topbar_search_avoids_help_and_avatar(self):
        from collections import defaultdict
        self.app.pal = defaultdict(int)
        for width in [72, 80, 120]:
            self.app.rects = []
            ui = s.UI(self.app, Mock())
            with patch.object(s, 'put'), patch.object(s, 'fill'):
                ui.topbar(0, width, max(24, min(32, width // 4)))
            rect = next(r for r in self.app.rects if r['act'] == 'focus_search')
            self.assertLess(rect['x1'], width - 9)

    def test_player_controls_do_not_overlap_volume_at_supported_widths(self):
        from collections import defaultdict
        self.app.pal = defaultdict(int)
        for width in [72, 80, 86, 104, 120]:
            self.app.rects = []
            ui = s.UI(self.app, Mock())
            with patch.object(s, 'put'), patch.object(s, 'fill'):
                ui.playerbar(20, width)
            seek = next(r for r in self.app.rects if r['act'] == 'seek')
            volume = next(r for r in self.app.rects if r['act'] == 'vol')
            self.assertLess(seek['x1'] + 5, volume['x0'])

    def test_sleep_timer_pauses_and_cancels_pending_load(self):
        self.app.mpv.cmd = Mock()
        with patch.object(s.time, 'monotonic', return_value=100):
            self.app.cycle_sleep()
        self.assertEqual(self.app.sleep_deadline, 1000)
        with patch.object(s.time, 'monotonic', return_value=1001):
            self.app.tick()
        self.assertIsNone(self.app.sleep_deadline)
        self.assertTrue(self.app.mpv.state['pause'])
        self.assertEqual(self.app.load_token, 1)

    def test_sleep_timer_cycles_off(self):
        for _ in range(5):
            self.app.cycle_sleep()
        self.assertIsNone(self.app.sleep_deadline)

    def test_volume_drag_clamps_and_releases(self):
        self.app.drag_rect = dict(act='vol', arg=(10, 10))
        with patch.object(s.curses, 'getmouse', return_value=(0, 40, 5, 0, s.curses.BUTTON1_RELEASED)):
            s.handle_mouse(self.app)
        self.assertEqual(self.app.store.volume, 100)
        self.assertIsNone(self.app.drag_rect)

    def test_modal_wheel_does_not_scroll_underlying_queue(self):
        self.app.mode = 'confirm_delete'
        self.app.move_sel = Mock()
        with patch.object(s.curses, 'getmouse', return_value=(0, 40, 5, 0, s.curses.BUTTON4_PRESSED)):
            s.handle_mouse(self.app)
        self.app.move_sel.assert_not_called()

    def test_picker_wheel_moves_picker(self):
        self.app.open_pick(track(1))
        self.app.pick_rows += [dict(name='One', new=False)]
        with patch.object(s.curses, 'getmouse', return_value=(0, 40, 5, 0, getattr(s.curses, 'BUTTON5_PRESSED', 0)), create=True):
            if getattr(s.curses, 'BUTTON5_PRESSED', 0):
                s.handle_mouse(self.app)
                self.assertEqual(self.app.pick_idx, 1)

    def test_radio_resets_shuffle_original_order(self):
        self.app.current = track(1)
        self.app.queue = [track(1), track(2)]
        self.app.shuffle = True
        self.app.orig_queue = [track(1), track(99)]
        with patch.object(s, '_ytdl_playlist', return_value=[track(3), track(4)]):
            self.app._radio_worker(track(1))
        self.app._apply_shuffle(False)
        self.assertCountEqual([t['id'] for t in self.app.queue], ['1', '3', '4'])

    def test_now_playing_toggle_returns_to_previous_view(self):
        self.app.push('liked')
        s.handle_key(self.app, 'f')
        self.assertEqual(self.app.stack[-1], ('playing', None))
        s.handle_key(self.app, 'f')
        self.assertEqual(self.app.stack[-1], ('liked', None))

    def test_reduced_motion_equalizer_is_static(self):
        self.app.reduced_motion = True
        self.app.frame = 0
        first = s.eq_bars(self.app)
        self.app.frame = 40
        self.assertEqual(s.eq_bars(self.app), first)

    def test_now_playing_empty_and_current_render(self):
        from collections import defaultdict
        self.app.pal = defaultdict(int)
        scr = Mock()
        scr.getmaxyx.return_value = (32, 120)
        ui = s.UI(self.app, scr)
        self.app.cover_for = Mock(return_value=None)
        with patch.object(s, 'put') as output, patch.object(s, 'draw_art'):
            ui.v_playing(3, 29, 30, 120)
            self.assertTrue(any('Search for a song' in str(c) for c in output.call_args_list))
            self.app.current = track(1)
            ui.v_playing(3, 29, 30, 120)
            self.assertTrue(any('Song 1' in str(c) for c in output.call_args_list))

    def test_help_pages_on_short_screen(self):
        from collections import defaultdict
        self.app.pal = defaultdict(int)
        scr = Mock()
        scr.getmaxyx.return_value = (16, 72)
        with patch.object(s, 'put') as output, patch.object(s, 'box'):
            s.UI(self.app, scr).help(3, 72)
        self.assertGreater(self.app.help_pages, 1)
        self.assertTrue(all(c.args[1] < 16 for c in output.call_args_list))
        self.app.show_help = True
        s.handle_key(self.app, 'j')
        self.assertEqual(self.app.help_page, 1)

    def test_play_next_and_reorder(self):
        self.app.queue = [track(i) for i in range(4)]
        self.app.qpos = 0
        self.app.current = self.app.queue[0]
        self.app.play_next(track(9))
        self.assertEqual(self.app.queue[1]['id'], '9')
        self.assertTrue(self.app.move_queue(1, 1))
        self.assertEqual([t['id'] for t in self.app.queue], ['0', '1', '9', '2', '3'])
        self.assertFalse(self.app.move_queue(1, -1))

    def test_non_finite_numbers_sanitized(self):
        s.STORE.write_text('{"liked":[{"id":"a","dur":1e999}],"last_search":1e999}')
        store = s.Store()
        self.assertIsNone(store.liked[0]['dur'])
        self.assertEqual(store.last_search, 0.0)


class MpvTests(unittest.TestCase):
    def test_stopped_player_cannot_restart(self):
        mpv = s.Mpv()
        mpv.stop()
        with patch.object(s.subprocess, 'Popen') as proc:
            self.assertFalse(mpv.ensure())
        proc.assert_not_called()

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


class ShuffleTests(unittest.TestCase):
    def test_artist_spacing_across_seeds(self):
        import random
        for seed in range(40):
            tracks = [dict(track(i), artist=str(i % 4)) for i in range(40)]
            result = s.smart_shuffle(tracks, rng=random.Random(seed))
            self.assertCountEqual(result, tracks)
            self.assertTrue(all(a['artist'] != b['artist'] for a, b in zip(result, result[1:])))

    def test_single_artist_and_duplicates_keep_all_entries(self):
        tracks = [track(1), track(1), track(2)]
        self.assertCountEqual(s.smart_shuffle(tracks), tracks)

    def test_avoids_current_artist_at_boundary(self):
        tracks = [dict(track(i), artist=str(i % 2)) for i in range(8)]
        result = s.smart_shuffle(tracks, previous_artist='0')
        self.assertEqual(result[0]['artist'], '1')

    def test_recent_songs_deferred_within_artist(self):
        result = s.smart_shuffle([track(i) for i in range(5)], recent_ids=['0', '1'])
        self.assertTrue(all(t['id'] not in ['0', '1'] for t in result[:3]))


if __name__ == '__main__':
    unittest.main()
