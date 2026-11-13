import json
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

    def test_speed_steps_clamp(self):
        self.app.mpv = Mock()
        for _ in range(9):
            s.handle_key(self.app, ']')
        self.assertEqual(self.app.speed, 2.0)
        self.app.mpv.set_speed.assert_called_with(2.0)
        for _ in range(9):
            s.handle_key(self.app, '[')
        self.assertEqual(self.app.speed, 0.75)

    def test_clear_upcoming_keeps_current_and_history(self):
        self.app.queue = [track(i) for i in range(5)]
        self.app.qpos = 2
        self.app.push('queue')
        s.handle_key(self.app, 'C')
        self.assertEqual([x['id'] for x in self.app.queue], ['0', '1', '2'])
        self.assertEqual(self.app.qpos, 2)
        s.handle_key(self.app, 'C')
        self.assertEqual(len(self.app.queue), 3)

    def test_export_playlist_writes_json(self):
        self.app.create_playlist('Road/Trip')
        self.app.add_to_playlist(0, track(1))
        with patch.object(s, 'EXPORT_DIR', Path(self.tmp.name) / 'out'):
            path = self.app.export_playlist(0)
        self.assertEqual(path.name, 'Road_Trip.json')
        data = s.json.loads(path.read_text(encoding='utf-8'))
        self.assertEqual(data['tracks'][0]['id'], '1')

    def test_import_playlist_roundtrip(self):
        src = Path(self.tmp.name) / 'in.json'
        src.write_text(s.json.dumps({'name': 'Mix', 'tracks': [track(1), {'bad': 1}]}), encoding='utf-8')
        ok, msg = s.import_playlist(src)
        self.assertTrue(ok, msg)
        st = s.Store()
        self.assertEqual(st.playlists[-1]['name'], 'Mix')
        self.assertEqual(len(st.playlists[-1]['tracks']), 1)

    def test_import_rejects_garbage(self):
        src = Path(self.tmp.name) / 'bad.json'
        src.write_text('[1,2]', encoding='utf-8')
        self.assertFalse(s.import_playlist(src)[0])

    def _mock_pal(self, can=True):
        self.app.pal = Mock()
        self.app.pal.can_theme.return_value = can
        self.app.pal.apply_theme.return_value = True

    def test_theme_picker_opens(self):
        self._mock_pal()
        s.handle_key(self.app, 'T')
        self.assertEqual(self.app.mode, 'theme')
        self.assertEqual(self.app.theme_orig, s.THEME_NAMES[0])

    def test_theme_picker_preview_and_keep(self):
        self._mock_pal()
        s.handle_key(self.app, 'T')
        s.handle_key(self.app, 'j')      # live preview
        self.app.pal.apply_theme.assert_called_with(s.THEME_NAMES[1])
        self.assertEqual(self.app.store.theme, s.THEME_NAMES[1])
        self.assertEqual(s.Store().theme, s.THEME_NAMES[0])  # not saved yet
        s.handle_key(self.app, '\n')    # keep
        self.assertEqual(self.app.mode, 'normal')
        self.assertEqual(s.Store().theme, s.THEME_NAMES[1])
        self.assertIn('Theme:', self.app.toast[0])

    def test_theme_picker_esc_reverts(self):
        self._mock_pal()
        s.handle_key(self.app, 'T')
        s.handle_key(self.app, 'j')
        s.handle_key(self.app, '\x1b')
        self.assertEqual(self.app.mode, 'normal')
        self.assertEqual(self.app.store.theme, s.THEME_NAMES[0])
        self.app.pal.apply_theme.assert_called_with(s.THEME_NAMES[0])

    def test_theme_picker_wraps(self):
        self._mock_pal()
        s.handle_key(self.app, 'T')
        s.handle_key(self.app, 'k')      # wraps to the last theme
        self.assertEqual(self.app.theme_idx, len(s.THEME_NAMES) - 1)

    def test_theme_refused_without_palette(self):
        self._mock_pal(can=False)
        s.handle_key(self.app, 'T')
        self.assertEqual(self.app.mode, 'normal')
        self.assertEqual(self.app.store.theme, s.THEME_NAMES[0])
        self.assertIn('palette', self.app.toast[0])

    def test_stats_summary_and_play_counts(self):
        plays = {'a': dict(title='A', artist='X', n=3), 'b': dict(title='B', artist='X', n=2),
                 'c': dict(title='C', artist='Y', n=4)}
        total, uniq, ta, ts = s.stats_summary(plays)
        self.assertEqual((total, uniq), (9, 3))
        self.assertEqual(ta[0], ('X', 5))
        self.assertEqual(ts[0], ('C', 'Y', 4, 'c'))

    def test_note_history_counts_and_persists(self):
        self.app._note_history(track(1))
        self.app._note_history(track(1))
        self.assertEqual(s.Store().plays['1']['n'], 2)

    def test_stats_key_opens_view(self):
        s.handle_key(self.app, 'i')
        self.assertEqual(self.app.stack[-1][0], 'stats')

    def test_shuffle_modes_keep_all_tracks_and_bias(self):
        import random
        tracks = [dict(id=str(i), title=str(i), artist='A' if i < 3 else 'B') for i in range(6)]
        plays = {'0': dict(n=9), '1': dict(n=9), '2': dict(n=9)}
        for mode in s.SHUFFLE_MODES:
            out = s.smart_shuffle(tracks, '', (), rng=random.Random(1), mode=mode, plays=plays)
            self.assertEqual(sorted(t['id'] for t in out), sorted(t['id'] for t in tracks))
        disc = s.smart_shuffle(tracks, '', (), rng=random.Random(1), mode='discovery', plays=plays)
        mood = s.smart_shuffle(tracks, '', (), rng=random.Random(1), mode='mood', plays=plays)
        self.assertEqual(disc[0]['artist'], 'B')
        self.assertEqual(mood[0]['artist'], 'A')

    def test_cycle_shuffle_mode_enables_and_persists(self):
        self.app.queue = [track(i) for i in range(4)]
        self.app.qpos = 0
        s.handle_key(self.app, 'S')
        self.assertTrue(self.app.shuffle)
        self.assertEqual(self.app.store.shuffle_mode, 'discovery')
        self.assertEqual(s.Store().shuffle_mode, 'discovery')
        self.assertEqual(sorted(t['id'] for t in self.app.queue), ['0', '1', '2', '3'])

    def test_reveal_frame_math(self):
        ui = s.UI.__new__(s.UI)
        ui.app = self.app
        ui.pal = {'text': 0}
        ui.scr = Mock()
        self.app.reduced_motion = False
        with patch.object(s, 'fill') as fill:
            self.app.frame = 5
            ui._reveal(3, 15, 0, 80)          # first sight: no animation
            self.assertFalse(fill.called)
            self.app.push('queue')
            self.app.frame = 6
            ui._reveal(3, 15, 0, 80)          # view changed: partial reveal
            self.assertTrue(fill.called)
            fill.reset_mock()
            self.app.frame = 6 + s.UI.REVEAL_FRAMES
            ui._reveal(3, 15, 0, 80)          # animation finished
            self.assertFalse(fill.called)
            fill.reset_mock()
            self.app.push('stats')
            self.app.reduced_motion = True
            self.app.frame += 1
            ui._reveal(3, 15, 0, 80)
            self.assertFalse(fill.called)

    def test_mpv_socket_uses_tempdir(self):
        with patch.object(s.tempfile, 'gettempdir', return_value='/data/tmp'):
            self.assertTrue(s.Mpv().sock_path.startswith('/data/tmp/spotui-'))

    def test_daily_mixes_from_library(self):
        st = self.app.store
        st.liked = [dict(track(i), artist='Alpha') for i in range(3)] + \
                   [dict(track(10 + i), artist='Beta') for i in range(3)] + [dict(track(99), artist='Solo')]
        st.plays = {'0': dict(title='t', artist='Alpha', n=5)}
        mixes = s.daily_mixes(st)
        self.assertEqual(mixes[0]['artist'], 'Alpha')
        self.assertEqual(len(mixes), 2)           # Solo has one song: no mix
        self.assertGreater(len(mixes[0]['tracks']), 3)
        self.assertEqual(len({t['id'] for t in mixes[0]['tracks']}), len(mixes[0]['tracks']))

    def test_mix_key_plays_on_home(self):
        self.app.store.liked = [dict(track(i), artist='Alpha') for i in range(3)]
        self.app._play_current = Mock()
        s.handle_key(self.app, '1')
        self.assertEqual(len(self.app.queue), 3)

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

    def test_picker_marks_playlists_already_having_the_song(self):
        t = track(1)
        self.app.store.playlists = [
            {"name": "Has it", "tracks": [dict(t)]},
            {"name": "Empty", "tracks": []}]
        self.app.open_pick(t)
        rows = self.app.pick_rows
        self.assertEqual(rows[1], {"name": "Has it", "new": False,
                                   "n": 1, "has": True, "pi": 0})
        self.assertEqual(rows[2], {"name": "Empty", "new": False,
                                   "n": 0, "has": False, "pi": 1})
        self.app.pal = {key: 0 for key in
                        ['dim', 'side', 'hover', 'sdim', 'sfaint', 'green']}
        scr = Mock()
        scr.getmaxyx.return_value = (40, 120)
        texts = []
        with patch.object(s, 'put',
                          side_effect=lambda sc, y, x, t_, *a, **k:
                          texts.append(str(t_))), \
                patch.object(s.curses, 'color_pair', return_value=0):
            s.UI(self.app, scr).pick_modal(35, 120)
        self.assertIn("\u2713 1", texts)
        self.assertIn("0", texts)

    def test_playlist_picker_scrolls_selected_item_into_view(self):
        self.app.pick_rows = [dict(name=str(i)) for i in range(25)]
        self.app.pick_idx = 24
        self.app.pal = {key: 0 for key in ['dim', 'side', 'hover', 'sdim', 'sfaint', 'green']}
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

    def test_autoplay_defaults_on_and_persists(self):
        self.assertTrue(self.app.store.autoplay)
        self.app.toggle_autoplay()
        self.assertFalse(self.app.store.autoplay)
        with patch.object(s.threading.Thread, 'start'):
            app2 = s.App()
        self.assertFalse(app2.store.autoplay)

    def test_prefetch_fires_only_on_last_song(self):
        self.app.queue = [track(1), track(2)]
        self.app.qpos = 0
        self.app.current = self.app.queue[0]
        with patch.object(s.threading.Thread, 'start') as th:
            self.app._maybe_autoplay()
        th.assert_not_called()
        self.app.qpos = 1
        self.app.current = self.app.queue[1]
        with patch.object(s.threading.Thread, 'start') as th:
            self.app._maybe_autoplay()
        th.assert_called_once()
        self.assertTrue(self.app._auto_busy)

    def test_prefetch_respects_toggle(self):
        self.app.store.autoplay = False
        self.app.queue = [track(1)]
        self.app.qpos = 0
        self.app.current = self.app.queue[0]
        with patch.object(s.threading.Thread, 'start') as th:
            self.app._maybe_autoplay()
        th.assert_not_called()
        self.assertFalse(self.app._auto_busy)

    def test_autoplay_appends_new_songs(self):
        self.app.current = track(1)
        self.app.queue = [track(1)]
        self.app.qpos = 0
        rev, tok = self.app.queue_revision, self.app.load_token
        with patch.object(s, '_ytdl_playlist', return_value=[track(2), track(3)]):
            self.app._auto_busy = True
            self.app._autoplay_worker(track(1), rev, tok)
        self.assertCountEqual([t['id'] for t in self.app.queue], ['1', '2', '3'])
        self.assertEqual(self.app.queue[0]['id'], '1')
        self.assertFalse(self.app._auto_busy)

    def test_play_records_source(self):
        self.app.play([track(1)], 0, source='Liked Songs')
        self.assertEqual(self.app.play_source, 'Liked Songs')
        self.app.play([track(2)], 0)
        self.assertIsNone(self.app.play_source)

    def test_source_for_vk(self):
        self.assertEqual(self.app._source_for_vk('history:'), 'Recently Played')
        self.assertEqual(self.app._source_for_vk('liked:'), 'Liked Songs')
        self.assertEqual(self.app._source_for_vk('artist:Muse'), 'Muse')
        self.assertIsNone(self.app._source_for_vk('queue:'))
        self.app.query = 'daft punk'
        self.assertEqual(self.app._source_for_vk('search:'),
                         'Search "daft punk"')
        self.app.store.playlists = [{'name': 'Gym', 'tracks': []}]
        self.assertEqual(self.app._source_for_vk('playlist:0'), 'Gym')
        self.assertEqual(self.app._source_for_vk('playlist:9'), 'Playlist')

    def test_drop_autoplayed(self):
        self.app.queue = [track(1), dict(track(2), auto=True), track(3),
                          dict(track(4), auto=True)]
        self.app.qpos = 2
        self.app.current = self.app.queue[2]
        self.app.drop_autoplayed()
        self.assertEqual([t['id'] for t in self.app.queue], ['1', '3'])
        self.assertEqual(self.app.qpos, 1)
        self.assertEqual(self.app.toast[0], 'Dropped 2 autoplayed songs')

    def test_drop_autoplayed_keeps_the_playing_song(self):
        self.app.queue = [dict(track(1), auto=True), dict(track(2), auto=True)]
        self.app.qpos = 0
        self.app.current = self.app.queue[0]
        self.app.drop_autoplayed()
        self.assertEqual([t['id'] for t in self.app.queue], ['1'])
        self.assertEqual(self.app.qpos, 0)
        self.app.drop_autoplayed()
        self.assertEqual(self.app.toast[0], 'No autoplayed songs to drop')

    def test_plays_for(self):
        plays = {'1': dict(title='A', artist='X', n=3),
                 '2': dict(title='B', artist='X', n=2)}
        self.assertEqual(s.plays_for([track(1), track(2)], plays), 5)
        self.assertEqual(s.plays_for([track(9)], plays), 0)
        self.assertEqual(s.plays_for([], plays), 0)

    def test_collection_header_counts_new_this_month(self):
        from collections import defaultdict
        ym = s.time.strftime("%Y-%m")
        self.app.store.liked = [dict(track(1), added=f"{ym}-03"),
                                dict(track(2), added=f"{ym}-11"),
                                dict(track(3), added="2020-05-01"),
                                track(4)]
        self.app.push('liked')
        self.app.pal = defaultdict(int)
        self.app.cover_for = Mock(return_value=None)
        scr = Mock()
        scr.getmaxyx.return_value = (40, 120)
        ui = s.UI(self.app, scr)
        ui.list_header = Mock()
        ui.track_list = Mock()
        ui.hint = Mock()
        texts = []
        with patch.object(s, 'put',
                          side_effect=lambda sc, y, x, t, *a, **k:
                          texts.append(str(t))), \
                patch.object(s, 'draw_art'):
            ui.v_collection(0, 30, 24, 120, 'liked', None)
        subs = [t for t in texts if 'new this month' in t]
        self.assertEqual(len(subs), 1)
        self.assertIn('2 new this month', subs[0])

    def test_artist_plays(self):
        self.app.store.plays = {
            '1': dict(title='A', artist='Luna Waves', n=3),
            '2': dict(title='B', artist='luna waves ', n=2),
            '3': dict(title='C', artist='Neon Coast', n=7),
        }
        self.assertEqual(self.app.artist_plays('Luna Waves'), 5)
        self.assertEqual(self.app.artist_plays('Unknown'), 0)

    def test_search_filter_defaults_to_all(self):
        self.assertEqual(self.app.search_filter, 'all')

    def test_remove_recent(self):
        self.app.store.recent = ['alpha', 'beta', 'gamma']
        self.app.remove_recent('beta')
        self.assertEqual(self.app.store.recent, ['alpha', 'gamma'])
        self.assertEqual(self.app.toast[0], 'Removed search: beta')
        self.app.remove_recent('not-there')   # no toast, no crash
        self.assertEqual(self.app.store.recent, ['alpha', 'gamma'])
        self.assertEqual(self.app.toast[0], 'Removed search: beta')

    def test_autoplay_marks_added_songs(self):
        self.app.current = track(1)
        self.app.queue = [track(1)]
        self.app.qpos = 0
        rev, tok = self.app.queue_revision, self.app.load_token
        with patch.object(s, '_ytdl_playlist', return_value=[track(2), track(3)]):
            self.app._auto_busy = True
            self.app._autoplay_worker(track(1), rev, tok)
        self.assertNotIn('auto', self.app.queue[0])
        self.assertTrue(all(t.get('auto') for t in self.app.queue[1:]))

    def test_queue_header_counts_upcoming_autoplayed(self):
        from collections import defaultdict
        self.app.current = track(1)
        self.app.queue = [track(1), track(2), track(3), track(4)]
        self.app.queue[0]['auto'] = True   # already playing: excluded
        self.app.queue[2]['auto'] = True
        self.app.queue[3]['auto'] = True
        self.app.qpos = 1
        self.app.pal = defaultdict(int)
        scr = Mock()
        scr.getmaxyx.return_value = (40, 120)
        ui = s.UI(self.app, scr)
        ui.hint = Mock()
        texts = []
        with patch.object(s, 'put',
                          side_effect=lambda sc, y, x, t, *a, **k:
                          texts.append(t)):
            ui.v_queue(0, 30, 24, 120)
        self.assertIn(f'  \u00b7  {s.IC_AUTO} 2 autoplayed (4 min)', texts)

    def test_autoplay_dedupes_queued_songs(self):
        self.app.current = track(1)
        self.app.queue = [track(1), track(2)]
        self.app.qpos = 1
        rev, tok = self.app.queue_revision, self.app.load_token
        with patch.object(s, '_ytdl_playlist', return_value=[track(2), track(3)]):
            self.app._autoplay_worker(track(1), rev, tok)
        self.assertCountEqual([t['id'] for t in self.app.queue], ['1', '2', '3'])

    def test_autoplay_dropped_after_queue_edit(self):
        self.app.current = track(1)
        self.app.queue = [track(1)]
        rev, tok = self.app.queue_revision, self.app.load_token
        self.app.add_queue(track(9))
        with patch.object(s, '_ytdl_playlist', return_value=[track(3)]):
            self.app._autoplay_worker(track(1), rev, tok)
        self.assertEqual([t['id'] for t in self.app.queue], ['1', '9'])

    def test_autoplay_advances_when_song_ended_during_fetch(self):
        self.app.current = track(1)
        self.app.queue = [track(1)]
        self.app.qpos = 0
        self.app.mpv.state['idle'] = True
        self.app.next = Mock()
        rev, tok = self.app.queue_revision, self.app.load_token
        with patch.object(s, '_ytdl_playlist', return_value=[track(2)]):
            self.app._autoplay_worker(track(1), rev, tok)
        self.app.next.assert_called_once_with(auto=True)

    def test_playlist_header_draws_cover_mosaic(self):
        from collections import defaultdict
        self.app.store.playlists = [dict(name='Mix', tracks=[track(i) for i in range(5)])]
        self.app.push('playlist', 0)
        self.app.pal = defaultdict(int)
        self.app.cover_for = Mock(return_value=None)
        scr = Mock()
        scr.getmaxyx.return_value = (40, 120)
        ui = s.UI(self.app, scr)
        ui.list_header = Mock()
        ui.track_list = Mock()
        ui.hint = Mock()
        with patch.object(s, 'draw_art') as da:
            ui.v_collection(0, 30, 24, 120, 'playlist', 0)
        seeds = [c.args[5] for c in da.call_args_list]
        self.assertEqual(seeds, ['0', '1', '2', '3'])

    def test_short_playlist_keeps_single_header_art(self):
        from collections import defaultdict
        self.app.store.playlists = [dict(name='Mix', tracks=[track(1), track(2)])]
        self.app.push('playlist', 0)
        self.app.pal = defaultdict(int)
        self.app.cover_for = Mock(return_value=None)
        scr = Mock()
        scr.getmaxyx.return_value = (40, 120)
        ui = s.UI(self.app, scr)
        ui.list_header = Mock()
        ui.track_list = Mock()
        ui.hint = Mock()
        with patch.object(s, 'draw_art') as da:
            ui.v_collection(0, 30, 24, 120, 'playlist', 0)
        self.assertEqual(len(da.call_args_list), 1)
        self.assertEqual(da.call_args_list[0].args[5], 'Mix')

    def _playing_ui(self, width=120):
        from collections import defaultdict
        self.app.queue = [track(1), track(2), track(3)]
        self.app.qpos = 0
        self.app.current = self.app.queue[0]
        self.app.pal = defaultdict(int)
        self.app.cover_for = Mock(return_value=None)
        scr = Mock()
        scr.getmaxyx.return_value = (40, 140)
        ui = s.UI(self.app, scr)
        ui.hint = Mock()
        return ui

    def test_now_playing_has_clickable_heart(self):
        ui = self._playing_ui()
        with patch.object(s, 'draw_art'):
            ui.v_playing(0, 34, 24, 120)
        hearts = [r for r in self.app.rects if r['act'] == 'likesong']
        self.assertEqual(len(hearts), 1)
        self.assertEqual(hearts[0]['arg']['id'], '1')

    def test_now_playing_heart_reflects_liked_state(self):
        ui = self._playing_ui()
        self.app.liked_ids.add('1')
        with patch.object(s, 'draw_art'), patch.object(s, 'put') as pt:
            ui.v_playing(0, 34, 24, 120)
        glyphs = [c.args[3] for c in pt.call_args_list]
        self.assertIn(s.IC_HEART, glyphs)

    def test_sidebar_marks_playing_source(self):
        from collections import defaultdict
        self.app.store.playlists = [{"name": "Late Night Drive",
                                     "tracks": [track(1)]},
                                    {"name": "Gym", "tracks": [track(2)]}]
        self.app.current = track(1)
        self.app.play_source = "Late Night Drive"
        self.app.mpv.state.update(idle=False)
        self.app.pal = defaultdict(int)
        scr = Mock()
        scr.getmaxyx.return_value = (40, 120)
        ui = s.UI(self.app, scr)
        calls = []
        with patch.object(s, 'put',
                          side_effect=lambda sc, y, x, t, *a, **k:
                          calls.append((y, x, str(t), k))), \
                patch.object(s.curses, 'color_pair', return_value=0):
            ui.sidebar(3, 33, 30)
        rows = {}
        for y, x, t, k in calls:
            rows.setdefault(y, []).append((x, t, k))
        marks = [y for y, cells in rows.items()
                 if any(t == "Late Night Drive" for _, t, _ in cells)
                 and any(t == s.eq_bars(self.app)[:3] for _, t, _ in cells)]
        self.assertEqual(len(marks), 1)
        gym = [y for y, cells in rows.items()
               if any(t == "Gym" for _, t, _ in cells)
               and any(t == s.eq_bars(self.app)[:3] for _, t, _ in cells)]
        self.assertEqual(gym, [])

    def test_home_hero_shows_play_count(self):
        from collections import defaultdict
        self.app.store.history = [dict(track(7), added=s.time.time())]
        self.app.store.plays = {"7": dict(title="Song 7", artist="A", n=12)}
        self.app.pal = defaultdict(int)
        self.app.cover_for = Mock(return_value=None)
        scr = Mock()
        scr.getmaxyx.return_value = (40, 140)
        ui = s.UI(self.app, scr)
        with patch.object(s, 'draw_art'), patch.object(s, 'put') as pt:
            ui._home_hero(self.app, ui.pal, scr, 4, 30, 24, 120)
        texts = [str(c.args[3]) for c in pt.call_args_list]
        self.assertTrue(any(t.endswith("12 plays") for t in texts), texts)

    def test_now_playing_up_next_shows_durations(self):
        ui = self._playing_ui()
        with patch.object(s, 'draw_art'), patch.object(s, 'put') as pt:
            ui.v_playing(0, 34, 24, 120)
        texts = [str(c.args[3]) for c in pt.call_args_list]
        self.assertGreaterEqual(texts.count("2:00"), 2)  # Song 2 and Song 3

    def test_now_playing_shows_play_count(self):
        ui = self._playing_ui()
        self.app.play_source = "Late Night Drive"
        self.app.store.plays = {"1": dict(title="Song 1", artist="A", n=45)}
        with patch.object(s, 'draw_art'), patch.object(s, 'put') as pt:
            ui.v_playing(0, 34, 24, 120)
        texts = [str(c.args[3]) for c in pt.call_args_list]
        self.assertIn("From Late Night Drive  \u00b7  45 plays", texts)

    def test_now_playing_no_play_count_when_unplayed(self):
        ui = self._playing_ui()
        self.app.play_source = "Late Night Drive"
        self.app.store.plays = {}
        with patch.object(s, 'draw_art'), patch.object(s, 'put') as pt:
            ui.v_playing(0, 34, 24, 120)
        texts = [str(c.args[3]) for c in pt.call_args_list]
        self.assertIn("From Late Night Drive", texts)

    def test_now_playing_narrow_shows_up_next(self):
        ui = self._playing_ui()
        self.app.rects = []
        with patch.object(s, 'draw_art'), patch.object(s, 'put') as pt:
            ui.v_playing(0, 34, 24, 64)   # width 40 < 56 -> narrow
        texts = [str(c.args[3]) for c in pt.call_args_list]
        self.assertIn('Next', texts)
        self.assertTrue(any('Song 2' in t for t in texts))
        jumps = [r for r in self.app.rects if r['act'] == 'qjump']
        self.assertTrue(jumps)

    def _playerbar_puts(self):
        from collections import defaultdict
        self.app.queue = [track(1)]
        self.app.current = track(1)
        self.app.mpv.state.update(pos=74.0, dur=200.0, idle=False)
        self.app.pal = defaultdict(int)
        scr = Mock()
        scr.getmaxyx.return_value = (40, 140)
        ui = s.UI(self.app, scr)
        with patch.object(s, 'draw_art'), patch.object(s, 'put') as pt:
            ui.playerbar(30, 120)
        return [str(c.args[3]) for c in pt.call_args_list]

    def test_playerbar_shows_elapsed_by_default(self):
        texts = self._playerbar_puts()
        self.assertIn('1:14', texts)
        self.assertNotIn('-2:06', texts)

    def test_playerbar_remaining_time_toggle(self):
        self.app.store.time_left = True
        texts = self._playerbar_puts()
        self.assertIn('-2:06', texts)
        self.assertNotIn('1:14', texts)

    def test_time_left_persists(self):
        self.app.store.time_left = True
        self.app.store.save()
        with patch.object(s.threading.Thread, 'start'):
            app2 = s.App()
        self.assertTrue(app2.store.time_left)

    def test_eq_cycles_and_applies_filter(self):
        self.app.mpv.cmd = Mock(return_value=True)
        self.assertEqual(self.app.store.eq_preset, 'off')
        self.app.cycle_eq()
        self.assertEqual(self.app.store.eq_preset, 'bass')
        self.app.mpv.cmd.assert_called_with(['set_property', 'af', s.EQ_FILTER['bass']])
        self.assertIn('Bass', self.app.toast[0])
        self.app.cycle_eq()
        self.app.cycle_eq()
        self.app.cycle_eq()
        self.assertEqual(self.app.store.eq_preset, 'off')
        self.app.mpv.cmd.assert_called_with(['set_property', 'af', ''])

    def test_eq_preset_persists(self):
        self.app.store.eq_preset = 'vocal'
        self.app.store.save()
        with patch.object(s.threading.Thread, 'start'):
            app2 = s.App()
        self.assertEqual(app2.store.eq_preset, 'vocal')

    def test_E_key_cycles_equalizer(self):
        s.handle_key(self.app, 'E')
        self.assertEqual(self.app.store.eq_preset, 'bass')

    def test_artist_fallback_fetches_for_unknown_artist(self):
        with patch.object(s, 'HAVE_YTDL', True), \
                patch.object(s.threading.Thread, 'start') as th:
            self.app.push('artist', 'Newcomer')
        th.assert_called_once()
        self.assertIn('Newcomer', self.app._artist_busy)

    def test_artist_fallback_skips_library_artists(self):
        self.app.store.liked = [track(1)]
        with patch.object(s, 'HAVE_YTDL', True), \
                patch.object(s.threading.Thread, 'start') as th:
            self.app.push('artist', 'Artist')
        th.assert_not_called()

    def test_artist_remote_results_fill_the_view(self):
        self.app.push('artist', 'Newcomer')
        with patch.object(s, 'ytdl_search', return_value=[track(7), track(8)]):
            self.app._artist_remote_worker('Newcomer')
        self.assertEqual([t['id'] for t in self.app.view_tracks()], ['7', '8'])
        self.assertNotIn('Newcomer', self.app._artist_busy)

    def test_artist_remote_failure_leaves_empty_view(self):
        self.app.push('artist', 'Newcomer')
        with patch.object(s, 'ytdl_search', side_effect=RuntimeError('x')):
            self.app._artist_remote_worker('Newcomer')
        self.assertEqual(self.app.view_tracks(), [])
        self.assertNotIn('Newcomer', self.app._artist_busy)

    def test_stats_week_counts_last_seven_days(self):
        import time as _t
        self.app.store.history = [
            dict(track(1), added=_t.time() - 3600),
            dict(track(2), added=_t.time() - 6 * 86400),
            dict(track(3), added=_t.time() - 9 * 86400),
            dict(track(4), added=None),
        ]
        self.assertEqual(s.stats_week(self.app.store), 2)

    def test_stats_week_tolerates_bad_timestamps(self):
        self.app.store.history = [dict(track(1), added='not-a-number'),
                                  dict(track(2), added=float('inf'))]
        self.assertEqual(s.stats_week(self.app.store), 0)

    def test_stats_days_buckets_by_local_day(self):
        import time as _t
        lt = _t.localtime()
        today0 = _t.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday,
                            0, 0, 0, 0, 0, -1))
        self.app.store.history = [
            dict(track(1), added=today0 + 3600),              # today
            dict(track(2), added=today0 + 7200),              # today
            dict(track(3), added=today0 - 3600),              # yesterday
            dict(track(4), added=today0 - 6 * 86400 + 60),    # 6 days ago
            dict(track(5), added=today0 - 9 * 86400),         # outside
            dict(track(6), added=None),
        ]
        days = s.stats_days(self.app.store)
        self.assertEqual(len(days), 7)
        self.assertEqual([n for _, n in days], [1, 0, 0, 0, 0, 1, 2])
        labels = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
        self.assertEqual([lab for lab, _ in days],
                         [labels[_t.localtime(today0 - (6 - i) * 86400).tm_wday]
                          for i in range(7)])

    def test_stats_days_tolerates_bad_timestamps(self):
        self.app.store.history = [dict(track(1), added='not-a-number'),
                                  dict(track(2), added=float('nan')),
                                  dict(track(3), added=float('inf'))]
        self.assertEqual([n for _, n in s.stats_days(self.app.store)],
                         [0] * 7)

    def test_seek_toast_shows_target_position(self):
        self.app.mpv.state.update(pos=74.0, dur=200.0)
        self.app.mpv.seek_rel = Mock()
        self.app.seek(10)
        self.app.mpv.seek_rel.assert_called_once_with(10)
        self.assertEqual(self.app.toast[0], "+10s - 1:24")

    def test_seek_toast_clamps_at_duration(self):
        self.app.mpv.state.update(pos=196.0, dur=200.0)
        self.app.mpv.seek_rel = Mock()
        self.app.seek(10)
        self.assertEqual(self.app.toast[0], "+10s - 3:20")

    def test_seek_backwards_floors_at_zero(self):
        self.app.mpv.state.update(pos=3.0, dur=200.0)
        self.app.mpv.seek_rel = Mock()
        self.app.seek(-10)
        self.assertEqual(self.app.toast[0], "-10s - 0:00")

    def test_volume_change_toasts_level(self):
        self.app.mpv.state["vol"] = 70
        self.app.vol(5)
        self.assertEqual(self.app.toast[0], "Volume 75")
        self.app.vol(-10)
        self.assertEqual(self.app.toast[0], "Volume 65")

    def test_toggle_mute_remembers_level(self):
        self.app.mpv.state["vol"] = 70
        self.app.toggle_mute()
        self.assertEqual(self.app.mpv.state["vol"], 0)
        self.assertEqual(self.app.toast[0], "Muted")
        self.app.toggle_mute()
        self.assertEqual(self.app.mpv.state["vol"], 70)
        self.assertEqual(self.app.toast[0], "Volume 70")

    def test_volume_change_unmutes(self):
        self.app.mpv.state["vol"] = 70
        self.app.toggle_mute()
        self.app.vol(5)
        self.assertIsNone(self.app._muted_from)
        self.assertEqual(self.app.mpv.state["vol"], 5)

    def test_u_key_toggles_autoplay(self):
        before = self.app.store.autoplay
        s.handle_key(self.app, 'u')
        self.assertEqual(self.app.store.autoplay, not before)

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

    def test_now_playing_artist_link_and_sleep_chip(self):
        from collections import defaultdict
        self.app.pal = defaultdict(int)
        scr = Mock()
        scr.getmaxyx.return_value = (40, 120)
        ui = s.UI(self.app, scr)
        self.app.cover_for = Mock(return_value=None)
        self.app.current = track(1)
        self.app.sleep_deadline = s.time.monotonic() + 600
        self.app.rects = []
        with patch.object(s, 'put') as output, patch.object(s, 'draw_art'):
            ui.v_playing(3, 29, 24, 120)
        texts = [str(c.args[3]) for c in output.call_args_list]
        self.assertTrue(any(t.startswith('Sleep ') for t in texts))
        hits = [r for r in self.app.rects
                if r['act'] == 'artist' and r['arg'] == 'Artist']
        self.assertTrue(hits)
        # the artist name is underlined so it reads as a link
        underlined = [c for c in output.call_args_list
                      if len(c.args) > 5 and c.args[3] == 'Artist'
                      and c.args[5] & s.curses.A_UNDERLINE]
        self.assertTrue(underlined)

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


class HistoryViewTests(unittest.TestCase):
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

    def test_fmt_added_handles_epoch_string_and_empty(self):
        import time as _t
        epoch = 1767225600
        self.assertEqual(s.fmt_added(epoch),
                         _t.strftime("%Y-%m-%d", _t.localtime(epoch)))
        self.assertEqual(s.fmt_added("2026-01-02"), "2026-01-02")
        self.assertEqual(s.fmt_added(None), "\u2014")
        self.assertEqual(s.fmt_added(0), "\u2014")

    def test_fmt_added_relative_labels(self):
        import time as _t
        now = _t.time()
        self.assertEqual(s.fmt_added(now), "Today")
        self.assertEqual(s.fmt_added(now - 86400), "Yesterday")
        three = now - 3 * 86400
        self.assertEqual(s.fmt_added(three),
                         _t.strftime("%a", _t.localtime(three)))
        old = now - 30 * 86400
        self.assertEqual(s.fmt_added(old),
                         _t.strftime("%Y-%m-%d", _t.localtime(old)))

    def test_history_view_tracks(self):
        t = track(1)
        self.app.store.history = [t]
        self.app.push("history")
        self.assertEqual(self.app.view_tracks(), [t])

    def test_y_opens_recently_played(self):
        s.handle_key(self.app, "y")
        self.assertEqual(self.app.stack[-1], ("history", None))


class LiveSearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for name, value in [('CFG', root), ('STORE', root / 'library.json'),
                            ('HAVE_YTDL', True)]:
            p = patch.object(s, name, value)
            p.start()
            self.addCleanup(p.stop)
        # keep Thread.start patched for the whole test: do_search spawns a
        # real worker otherwise, and it flips searching=False before the
        # assertions read it (raced in CI)
        tp = patch.object(s.threading.Thread, 'start')
        tp.start()
        self.addCleanup(tp.stop)
        self.app = s.App()
        self.app.refresh_similar = Mock()
        self.app.push("search")
        self.app.mode = "search"
        self.app.query = "hello"

    def test_fires_after_debounce_without_recording(self):
        self.app._edit_t = s.time.time() - 1.0
        self.app.tick()
        self.assertTrue(self.app.searching)
        self.assertEqual(self.app.live_q, "hello")
        self.assertEqual(self.app.store.recent, [])       # live != submitted
        self.app.refresh_similar.assert_not_called()

    def test_waits_for_debounce(self):
        self.app._edit_t = s.time.time()
        self.app.tick()
        self.assertFalse(self.app.searching)
        self.assertEqual(self.app.live_q, "")

    def test_skips_query_already_showing(self):
        self.app.live_q = "hello"
        self.app._edit_t = s.time.time() - 1.0
        self.app.tick()
        self.assertFalse(self.app.searching)

    def test_no_live_search_outside_search_mode(self):
        self.app.mode = "normal"
        self.app._edit_t = s.time.time() - 1.0
        self.app.tick()
        self.assertFalse(self.app.searching)

    def test_submit_records_without_second_search(self):
        self.app.live_q = "hello"
        s.handle_key(self.app, "\n")
        self.assertEqual(self.app.mode, "normal")
        self.assertEqual(self.app.store.recent[0], "hello")
        self.assertFalse(self.app.searching)             # results already live
        self.app.refresh_similar.assert_called_once()

    def test_submit_new_query_searches_and_records(self):
        s.handle_key(self.app, "\n")
        self.assertEqual(self.app.mode, "normal")
        self.assertTrue(self.app.searching)
        self.assertEqual(self.app.store.recent[0], "hello")

    def test_keystrokes_bump_edit_time(self):
        self.app._edit_t = 0.0
        s.handle_key(self.app, "!")
        self.assertGreater(self.app._edit_t, 0.0)
        self.assertEqual(self.app.query, "hello!")


class FuzzRegressionTests(unittest.TestCase):
    """Crashes found by adversarial fuzzing of the format helpers."""

    def test_fmt_t_survives_non_finite_and_huge(self):
        dash = s.fmt_t(None)
        self.assertEqual(s.fmt_t(float("inf")), dash)
        self.assertEqual(s.fmt_t(float("nan")), dash)
        self.assertTrue(s.fmt_t(-3))                     # no exception
        self.assertTrue(s.fmt_t(10**18))                 # no exception

    def test_fmt_added_survives_non_finite_and_huge(self):
        self.assertEqual(s.fmt_added(float("inf")), "\u2014")
        self.assertEqual(s.fmt_added(float("nan")), "\u2014")
        self.assertEqual(s.fmt_added(10**18), "\u2014")
        self.assertEqual(s.fmt_added(-5), "\u2014")
        self.assertEqual(s.fmt_added(True), "\u2014")
        self.assertEqual(s.fmt_added(""), "\u2014")


class ArtistViewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for name, value in [('CFG', root), ('STORE', root / 'library.json')]:
            p = patch.object(s, name, value)
            p.start()
            self.addCleanup(p.stop)
        tp = patch.object(s.threading.Thread, 'start')
        tp.start()
        self.addCleanup(tp.stop)
        self.app = s.App()
        self.app.refresh_similar = Mock()

    def _lib(self):
        a = dict(track(1), artist="Luna Waves")
        b = dict(track(2), artist="luna waves ")
        c = dict(track(3), artist="Other")
        self.app.store.liked = [a]
        self.app.store.history = [dict(track(1), artist="Luna Waves"), c]
        self.app.store.playlists = [{"name": "P", "tracks": [b]}]
        return a, b, c

    def test_artist_tracks_dedupes_and_matches_casefold(self):
        self._lib()
        out = self.app.artist_tracks("LUNA waves")
        self.assertEqual([t["id"] for t in out], ["1", "2"])

    def test_view_tracks_artist(self):
        self._lib()
        self.app.push("artist", "Luna Waves")
        self.assertEqual(len(self.app.view_tracks()), 2)

    def test_popular_section_orders_by_plays_and_plays(self):
        from collections import defaultdict
        self.app.store.liked = [dict(track(1), artist="Luna Waves"),
                                dict(track(2), artist="Luna Waves"),
                                dict(track(3), artist="Luna Waves")]
        self.app.store.plays = {
            "1": dict(title="Song 1", artist="Luna Waves", n=2),
            "2": dict(title="Song 2", artist="Luna Waves", n=9),
            "3": dict(title="Song 3", artist="Luna Waves", n=5)}
        self.app.push("artist", "Luna Waves")
        self.app.pal = defaultdict(int)
        self.app.cover_for = Mock(return_value=None)
        scr = Mock()
        scr.getmaxyx.return_value = (40, 120)
        ui = s.UI(self.app, scr)
        ui.hint = Mock()
        self.app.rects = []
        texts = []
        with patch.object(s, 'put',
                          side_effect=lambda sc, y, x, t, *a, **k:
                          texts.append(str(t))), \
                patch.object(s, 'draw_art'):
            ui.v_artist(0, 34, 24, 120)
        self.assertIn("POPULAR", texts)
        i = texts.index("POPULAR")
        self.assertEqual(texts[i + 1:i + 4], ["1", "Song 2", "9 plays"])
        hits = [r for r in self.app.rects if r["act"] == "playat"]
        self.assertEqual(len(hits), 3)
        self.app.play = Mock()
        r = hits[0]
        with patch.object(s.curses, 'getmouse',
                          return_value=(0, r["x0"] + 1, r["y0"], 0,
                                        s.curses.BUTTON1_CLICKED)):
            s.handle_mouse(self.app)
        self.app.play.assert_called_once()
        tracks_arg, pos_arg = self.app.play.call_args[0][:2]
        self.assertEqual(pos_arg, 0)
        self.assertEqual(tracks_arg[0]["id"], "2")

    def test_popular_highlights_currently_playing(self):
        from collections import defaultdict
        self.app.store.liked = [dict(track(1), artist="Luna Waves"),
                                dict(track(2), artist="Luna Waves"),
                                dict(track(3), artist="Luna Waves")]
        self.app.store.plays = {
            "1": dict(title="Song 1", artist="Luna Waves", n=2),
            "2": dict(title="Song 2", artist="Luna Waves", n=9),
            "3": dict(title="Song 3", artist="Luna Waves", n=5)}
        self.app.current = self.app.store.liked[1]
        self.app.mpv.state["idle"] = False
        self.app.push("artist", "Luna Waves")
        self.app.pal = defaultdict(int)
        self.app.cover_for = Mock(return_value=None)
        scr = Mock()
        scr.getmaxyx.return_value = (40, 120)
        ui = s.UI(self.app, scr)
        ui.hint = Mock()
        self.app.rects = []
        calls = []
        with patch.object(s, 'put',
                          side_effect=lambda sc, y, x, t, *a, **k:
                          calls.append((y, x, str(t), a, k))), \
                patch.object(s, 'draw_art'):
            ui.v_artist(0, 34, 24, 120)
        # the popular section sits above the full list: its "Song 2" row is
        # the topmost one, bold, with eq bars instead of the rank number
        titles = sorted((y, a) for y, x, t, a, k in calls
                        if x == 29 and t == "Song 2")
        self.assertEqual(len(titles), 1)   # only the popular row is at x=29
        py, pa = titles[0]
        self.assertTrue(pa[1] & s.curses.A_BOLD)
        nums = [t for y, x, t, a, k in calls
                if y == py and x == 26]
        self.assertEqual(nums, [s.eq_bars(self.app)[:3]])

    def test_artist_page_lists_other_played_artists(self):
        from collections import defaultdict
        self.app.store.liked = [dict(track(1), artist="Luna Waves"),
                                dict(track(2), artist="Luna Waves")]
        self.app.store.plays = {
            "1": dict(title="S1", artist="Luna Waves", n=9),
            "2": dict(title="S2", artist="Luna Waves", n=5),
            "3": dict(title="S3", artist="Neon Coast", n=7),
            "4": dict(title="S4", artist="Glass Rivers", n=3)}
        self.app.push("artist", "Luna Waves")
        self.app.pal = defaultdict(int)
        self.app.cover_for = Mock(return_value=None)
        scr = Mock()
        scr.getmaxyx.return_value = (40, 120)
        ui = s.UI(self.app, scr)
        ui.hint = Mock()
        self.app.rects = []
        texts = []
        with patch.object(s, 'put',
                          side_effect=lambda sc, y, x, t, *a, **k:
                          texts.append(str(t))), \
                patch.object(s, 'draw_art'):
            ui.v_artist(0, 34, 24, 120)
        self.assertIn("MORE ARTISTS YOU PLAY", texts)
        self.assertIn("Neon Coast", texts)   # most played first
        self.assertIn("Glass Rivers", texts)
        chips = [r["arg"] for r in self.app.rects
                 if r["act"] == "artist" and r["y0"] == 12]
        self.assertEqual(chips, ["Neon Coast", "Glass Rivers"])

    def test_o_opens_artist_of_selection(self):
        self._lib()
        self.app.push("liked")
        s.handle_key(self.app, "o")
        self.assertEqual(self.app.stack[-1], ("artist", "Luna Waves"))

    def test_o_without_track_toasts(self):
        s.handle_key(self.app, "o")
        self.assertEqual(self.app.stack[-1], ("home", None))

    def test_enter_on_empty_artist_searches_youtube(self):
        with patch.object(s, "HAVE_YTDL", True):
            self.app.push("artist", "Nobody Here")
            s.handle_key(self.app, "\n")
            self.assertEqual(self.app.mode, "search")
            self.assertEqual(self.app.query, "Nobody Here")
            self.assertTrue(self.app.searching)

    def test_play_from_artist_starts_radio(self):
        self._lib()
        self.app.push("artist", "Luna Waves")
        self.app._start_radio = Mock()
        self.app.play_row("artist:Luna Waves", 1)
        self.assertEqual(self.app.current["id"], "2")
        self.app._start_radio.assert_called_once()


class SearchArtistChipTests(unittest.TestCase):
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

    def test_matches_substring_casefold_library_first(self):
        self.app.store.liked = [dict(track(1), artist="Luna Waves")]
        self.app.store.history = [dict(track(2), artist="luna waves")]
        self.app.results = [dict(track(3), artist="Lunar Echo"),
                            dict(track(4), artist="Other")]
        self.assertEqual(self.app.search_artists("LUNA"),
                         ["Luna Waves", "Lunar Echo"])

    def test_empty_query_and_limit(self):
        self.assertEqual(self.app.search_artists(""), [])
        self.app.store.liked = [dict(track(i), artist=f"Art {i}")
                                for i in range(10)]
        self.assertEqual(len(self.app.search_artists("art")), 5)

    def _render_search(self, query):
        from collections import defaultdict
        self.app.pal = defaultdict(int)
        self.app.query = query
        self.app.search_filter = "all"
        self.app.searching = False
        self.app.cover_for = Mock(return_value=None)
        scr = Mock()
        scr.getmaxyx.return_value = (40, 120)
        ui = s.UI(self.app, scr)
        ui.list_header = Mock()
        ui.track_list = Mock()
        ui.hint = Mock()
        texts = []
        with patch.object(s, 'put',
                          side_effect=lambda sc, y, x, t, *a, **k:
                          texts.append(str(t))), \
                patch.object(s, 'draw_art'):
            ui.v_search(0, 30, 24, 120)
        return texts

    def test_top_result_is_artist_on_strong_match(self):
        self.app.store.liked = [dict(track(1), artist="Luna Waves")]
        self.app.results = [dict(track(1), artist="Luna Waves"),
                            dict(track(2), artist="Other")]
        texts = self._render_search("luna")
        self.assertIn("Luna Waves", texts)
        self.assertIn("Artist \u2022 1 songs", texts)
        self.assertNotIn("Song \u2022 Luna Waves", texts)

    def test_top_result_stays_song_on_weak_match(self):
        self.app.store.liked = [dict(track(1), artist="Luna Waves")]
        self.app.results = [dict(track(1), artist="Luna Waves"),
                            dict(track(2), artist="Other")]
        texts = self._render_search("waves")  # substring, not prefix
        self.assertIn("Song \u2022 Luna Waves", texts)
        self.assertNotIn("Artist \u2022 1 songs", texts)

    def test_no_results_offers_recent_searches(self):
        self.app.store.recent = ["midnight", "rain"]
        self.app.results = []
        self.app.rects = []
        texts = self._render_search("zzzz nothing")
        self.assertIn("Recent searches", texts)
        self.assertIn("midnight", texts)
        hits = [r for r in self.app.rects
                if r["act"] == "recent" and r["arg"] == "midnight"]
        self.assertTrue(hits)


class ZenModeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for name, value in [('CFG', root), ('STORE', root / 'library.json')]:
            p = patch.object(s, name, value)
            p.start()
            self.addCleanup(p.stop)
        tp = patch.object(s.threading.Thread, 'start')
        tp.start()
        self.addCleanup(tp.stop)
        self.app = s.App()

    def test_toggle_persists(self):
        self.assertFalse(self.app.store.zen)
        self.app.toggle_zen()
        self.assertTrue(self.app.store.zen)
        st = s.Store()
        self.assertTrue(st.zen)
        self.app.toggle_zen()
        self.assertFalse(self.app.store.zen)


class PickFilterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for name, value in [('CFG', root), ('STORE', root / 'library.json')]:
            p = patch.object(s, name, value)
            p.start()
            self.addCleanup(p.stop)
        tp = patch.object(s.threading.Thread, 'start')
        tp.start()
        self.addCleanup(tp.stop)
        self.app = s.App()
        self.app.store.playlists = [
            {"name": "Late Night Drive", "tracks": []},
            {"name": "Gym", "tracks": []},
            {"name": "Focus", "tracks": []}]
        self.track = {"id": "t1", "title": "Song", "artist": "A",
                      "dur": 100}

    def test_filter_narrows_view_and_keeps_new_row(self):
        self.app.open_pick(self.track)
        self.app.pick_filter = "g"
        names = [r["name"] for r in self.app.pick_view()]
        self.assertEqual(names, ["+ New playlist", "Late Night Drive", "Gym"])
        self.app.pick_filter = "foc"
        names = [r["name"] for r in self.app.pick_view()]
        self.assertEqual(names, ["+ New playlist", "Focus"])

    def test_typing_filters_and_enter_adds_to_right_playlist(self):
        self.app.open_pick(self.track)
        for ch in "gym":
            s.handle_key(self.app, ch)
        self.assertEqual(self.app.pick_filter, "gym")
        self.assertEqual([r["name"] for r in self.app.pick_view()],
                         ["+ New playlist", "Gym"])
        s.handle_key(self.app, "j" if not self.app.pick_filter else
                     s.curses.KEY_DOWN)
        s.handle_key(self.app, "\n")
        self.assertEqual(self.app.mode, "normal")
        self.assertEqual(self.app.store.playlists[1]["tracks"][0]["id"], "t1")

    def test_esc_clears_filter_before_closing(self):
        self.app.open_pick(self.track)
        self.app.pick_filter = "g"
        s.handle_key(self.app, "\x1b")
        self.assertEqual(self.app.mode, "pick")
        self.assertEqual(self.app.pick_filter, "")
        s.handle_key(self.app, "\x1b")
        self.assertEqual(self.app.mode, "normal")


class SearchPlaylistsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for name, value in [('CFG', root), ('STORE', root / 'library.json')]:
            p = patch.object(s, name, value)
            p.start()
            self.addCleanup(p.stop)
        tp = patch.object(s.threading.Thread, 'start')
        tp.start()
        self.addCleanup(tp.stop)
        self.app = s.App()
        self.app.store.playlists = [
            {"name": "Late Night Drive", "tracks": [1]},
            {"name": "Gym", "tracks": [1, 2]},
            {"name": "gym classics", "tracks": []},
            {"name": "Focus", "tracks": []}]

    def test_matches_casefold_and_keeps_indices(self):
        got = self.app.search_playlists("GYM")
        self.assertEqual([(i, p["name"]) for i, p in got],
                         [(1, "Gym"), (2, "gym classics")])

    def test_empty_and_blank_query_match_nothing(self):
        self.assertEqual(self.app.search_playlists(""), [])
        self.assertEqual(self.app.search_playlists("   "), [])

    def test_limit_caps_results(self):
        self.assertEqual(len(self.app.search_playlists("gym", limit=1)), 1)


class SidebarStatsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for name, value in [('CFG', root), ('STORE', root / 'library.json')]:
            p = patch.object(s, name, value)
            p.start()
            self.addCleanup(p.stop)
        tp = patch.object(s.threading.Thread, 'start')
        tp.start()
        self.addCleanup(tp.stop)
        self.app = s.App()
        self.app.pal = {key: 0 for key in
                        ['side', 'sgreen', 'pill', 'sdim', 'sfaint',
                         'pilldim', 'pgreen']}

    def test_sidebar_shows_stats_nav(self):
        scr = Mock()
        texts = []
        with patch.object(s, 'put',
                          side_effect=lambda sc, y, x, t_, *a, **k:
                          texts.append(str(t_))), \
                patch.object(s, 'fill'), \
                patch.object(s.curses, 'color_pair', return_value=0):
            s.UI(self.app, scr).sidebar(3, 34, 30)
        self.assertIn("Stats", texts)
        navs = [r['arg'] for r in self.app.rects if r['act'] == 'nav']
        self.assertIn("stats", navs)

    def test_stats_nav_pushes_stats_view(self):
        self.app.push("stats")
        self.assertEqual(self.app.stack[-1][0], "stats")


class HomeOnRepeatTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for name, value in [('CFG', root), ('STORE', root / 'library.json')]:
            p = patch.object(s, name, value)
            p.start()
            self.addCleanup(p.stop)
        tp = patch.object(s.threading.Thread, 'start')
        tp.start()
        self.addCleanup(tp.stop)
        self.app = s.App()
        self.app.pal = {key: 0 for key in ['text', 'faint', 'dim', 'green']}
        now = s.time.time()
        self.app.store.history = [
            {"id": "a", "title": "Alpha", "artist": "A", "dur": 100,
             "added": now - 3600},
            {"id": "a", "title": "Alpha", "artist": "A", "dur": 100,
             "added": now - 7200},
            {"id": "b", "title": "Beta", "artist": "B", "dur": 100,
             "added": now - 3600},
            {"id": "b", "title": "Beta", "artist": "B", "dur": 100,
             "added": now - 7200}]

    def _draw(self):
        self.app.cover_for = lambda *a, **k: None
        scr = Mock()
        texts = []
        with patch.object(s, 'put',
                          side_effect=lambda sc, y, x, t_, *a, **k:
                          texts.append(str(t_))), \
                patch.object(s, 'fill'), patch.object(s, 'draw_art'), \
                patch.object(s.curses, 'color_pair', return_value=0):
            s.UI(self.app, scr)._home_heavy(self.app, self.app.pal, scr,
                                            0, 30, 0, 120)
        return texts

    def test_shelf_shows_title_and_counts(self):
        texts = self._draw()
        self.assertIn("On repeat", texts)
        self.assertIn("Alpha", texts)
        self.assertTrue(any("A \u00b7 2 plays" in x for x in texts))

    def test_empty_history_draws_nothing(self):
        self.app.store.history = []
        self.assertEqual(self._draw(), [])


class HomeStreakTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for name, value in [('CFG', root), ('STORE', root / 'library.json')]:
            p = patch.object(s, name, value)
            p.start()
            self.addCleanup(p.stop)
        tp = patch.object(s.threading.Thread, 'start')
        tp.start()
        self.addCleanup(tp.stop)
        self.app = s.App()
        self.app.pal = {key: 0 for key in ['text', 'faint', 'accent', 'green']}

    def _greeting_texts(self):
        scr = Mock()
        ui = s.UI(self.app, scr)
        for m in ("_home_hero", "_home_tiles", "_home_mixes", "_home_similar",
                  "_home_heavy", "_home_history", "_home_liked",
                  "_home_recent"):
            setattr(ui, m, lambda *a, **k: 5)
        texts = []
        with patch.object(s, 'put',
                          side_effect=lambda sc, y, x, t_, *a, **k:
                          texts.append(str(t_))), \
                patch.object(s, 'fill'), \
                patch.object(s.curses, 'color_pair', return_value=0):
            ui.v_home(0, 40, 0, 120)
        return texts

    def test_streak_shown_from_two_days(self):
        now = s.time.time()
        self.app.store.history = [
            {"id": "a", "title": "A", "artist": "X", "dur": 1,
             "added": now - 3600},
            {"id": "b", "title": "B", "artist": "X", "dur": 1,
             "added": now - 90000}]
        self.assertTrue(any("2-day streak" in x
                            for x in self._greeting_texts()))

    def test_no_streak_when_only_today(self):
        now = s.time.time()
        self.app.store.history = [
            {"id": "a", "title": "A", "artist": "X", "dur": 1,
             "added": now - 3600}]
        self.assertFalse(any("streak" in x
                             for x in self._greeting_texts()))


class ClearHistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for name, value in [('CFG', root), ('STORE', root / 'library.json')]:
            p = patch.object(s, name, value)
            p.start()
            self.addCleanup(p.stop)
        tp = patch.object(s.threading.Thread, 'start')
        tp.start()
        self.addCleanup(tp.stop)
        self.app = s.App()
        self.app.store.history = [
            {"id": "a", "title": "A", "artist": "X", "dur": 1,
             "added": s.time.time()}]
        self.app.store.plays = {"a": {"n": 3, "title": "A", "artist": "X"}}
        self.app.store.liked = [
            {"id": "a", "title": "A", "artist": "X", "dur": 1}]
        self.app.store.playlists = [{"name": "Keep", "tracks": [
            {"id": "a", "title": "A", "artist": "X", "dur": 1}]}]

    def test_clear_history_keeps_library(self):
        self.app.clear_history()
        self.assertEqual(self.app.store.history, [])
        self.assertEqual(self.app.store.plays, {})
        self.assertEqual(len(self.app.store.liked), 1)
        self.assertEqual(self.app.store.playlists[0]["name"], "Keep")
        st = s.Store()
        self.assertEqual(st.history, [])
        self.assertEqual(st.plays, {})

    def test_confirm_keys(self):
        self.app.mode = "confirm_clearhist"
        s.handle_key(self.app, "n")
        self.assertEqual(self.app.mode, "normal")
        self.assertEqual(len(self.app.store.history), 1)
        self.app.mode = "confirm_clearhist"
        s.handle_key(self.app, "y")
        self.assertEqual(self.app.mode, "normal")
        self.assertEqual(self.app.store.history, [])


class FirstPlayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for name, value in [('CFG', root), ('STORE', root / 'library.json')]:
            p = patch.object(s, name, value)
            p.start()
            self.addCleanup(p.stop)
        tp = patch.object(s.threading.Thread, 'start')
        tp.start()
        self.addCleanup(tp.stop)
        self.app = s.App()

    def test_first_play_set_once(self):
        t1 = {"id": "a", "title": "A", "artist": "X", "dur": 1,
              "url": "u"}
        self.app._note_history(t1)
        first = self.app.store.first_play
        self.assertIsNotNone(first)
        self.app._note_history({"id": "b", "title": "B", "artist": "X",
                                "dur": 1, "url": "u"})
        self.assertEqual(self.app.store.first_play, first)

    def test_first_play_survives_reload(self):
        self.app.store.first_play = 1700000000.0
        self.app.store.save()
        self.assertEqual(s.Store().first_play, 1700000000.0)

    def test_bad_first_play_ignored(self):
        self.app.store.first_play = "nope"
        self.app.store.save()
        self.assertIsNone(s.Store().first_play)


class MuteKeyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for name, value in [('CFG', root), ('STORE', root / 'library.json')]:
            p = patch.object(s, name, value)
            p.start()
            self.addCleanup(p.stop)
        tp = patch.object(s.threading.Thread, 'start')
        tp.start()
        self.addCleanup(tp.stop)
        self.app = s.App()

    def test_m_key_mutes_and_restores(self):
        self.app.mpv.state["vol"] = 70
        s.handle_key(self.app, "M")
        self.assertEqual(self.app.mpv.state["vol"], 0)
        self.assertEqual(self.app._muted_from, 70)
        s.handle_key(self.app, "M")
        self.assertEqual(self.app.mpv.state["vol"], 70)
        self.assertIsNone(self.app._muted_from)


class SearchTabFilterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for name, value in [('CFG', root), ('STORE', root / 'library.json')]:
            p = patch.object(s, name, value)
            p.start()
            self.addCleanup(p.stop)
        tp = patch.object(s.threading.Thread, 'start')
        tp.start()
        self.addCleanup(tp.stop)
        self.app = s.App()
        self.app.mode = "search"

    def test_tab_cycles_filters(self):
        self.assertEqual(self.app.search_filter, "all")
        s.handle_key(self.app, "\t")
        self.assertEqual(self.app.search_filter, "songs")
        s.handle_key(self.app, "\t")
        self.assertEqual(self.app.search_filter, "artists")
        s.handle_key(self.app, "\t")
        self.assertEqual(self.app.search_filter, "all")

    def test_tab_does_not_enter_query(self):
        s.handle_key(self.app, "\t")
        self.assertEqual(self.app.query, "")


class SimilarViewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for name, value in [('CFG', root), ('STORE', root / 'library.json')]:
            p = patch.object(s, name, value)
            p.start()
            self.addCleanup(p.stop)
        tp = patch.object(s.threading.Thread, 'start')
        tp.start()
        self.addCleanup(tp.stop)
        self.app = s.App()
        self.app.store.similar = {
            "seed": "Luna Waves", "kind": "artist",
            "items": [{"id": "x", "title": "Pick", "artist": "Luna Waves",
                       "dur": 100, "url": "u"}]}

    def test_r_on_home_opens_made_for_you(self):
        s.handle_key(self.app, "R")
        self.assertEqual(self.app.stack[-1][0], "similar")

    def test_r_inside_refreshes(self):
        self.app.push("similar")
        with patch.object(self.app, 'refresh_similar') as rs:
            s.handle_key(self.app, "R")
        rs.assert_called_once_with(force=True)

    def test_view_tracks_returns_items(self):
        tracks = self.app.view_tracks("similar:")
        self.assertEqual([t["id"] for t in tracks], ["x"])

    def test_empty_state_draws_hint(self):
        self.app.store.similar = {}
        self.app.push("similar")
        self.app.pal = {key: 0 for key in ['text', 'faint', 'dim']}
        scr = Mock()
        texts = []
        with patch.object(s, 'put',
                          side_effect=lambda sc, y, x, t_, *a, **k:
                          texts.append(str(t_))), \
                patch.object(s, 'fill'), \
                patch.object(s.curses, 'color_pair', return_value=0):
            s.UI(self.app, scr).v_similar(0, 30, 0, 120)
        self.assertTrue(any("No picks yet" in x for x in texts))


class ChipActionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for name, value in [('CFG', root), ('STORE', root / 'library.json')]:
            p = patch.object(s, name, value)
            p.start()
            self.addCleanup(p.stop)
        tp = patch.object(s.threading.Thread, 'start')
        tp.start()
        self.addCleanup(tp.stop)
        self.app = s.App()

    def test_speed_chip_resets_to_normal(self):
        self.app.speed = 1.5
        self.app.chip_action("speed")
        self.assertEqual(self.app.speed, 1.0)

    def test_repeat_chip_cycles(self):
        before = self.app.repeat
        self.app.chip_action("repeat")
        self.assertNotEqual(self.app.repeat, before)

    def test_shuffle_chip_toggles(self):
        before = self.app.shuffle
        self.app.chip_action("shuffle")
        self.assertNotEqual(self.app.shuffle, before)

    def test_eq_chip_cycles(self):
        before = self.app.store.eq_preset
        self.app.chip_action("eq")
        self.assertNotEqual(self.app.store.eq_preset, before)

    def test_autoplay_chip_toggles(self):
        before = self.app.store.autoplay
        self.app.chip_action("autoplay")
        self.assertNotEqual(self.app.store.autoplay, before)

    def test_unknown_chip_raises_keyerror(self):
        self.assertRaises(KeyError, self.app.chip_action, "nope")


class HomePolishTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for name, value in [('CFG', root), ('STORE', root / 'library.json')]:
            p = patch.object(s, name, value)
            p.start()
            self.addCleanup(p.stop)
        tp = patch.object(s.threading.Thread, 'start')
        tp.start()
        self.addCleanup(tp.stop)
        self.app = s.App()
        self.app.cover_for = lambda *a, **k: None

    def test_on_repeat_links_to_stats(self):
        now = s.time.time()
        self.app.store.history = [
            {"id": "a", "title": "A", "artist": "X", "dur": 1,
             "added": now - 3600},
            {"id": "a", "title": "A", "artist": "X", "dur": 1,
             "added": now - 7200}]
        self.app.pal = {key: 0 for key in ['text', 'faint', 'dim', 'green']}
        scr = Mock()
        with patch.object(s, 'put'), patch.object(s, 'fill'), \
                patch.object(s, 'draw_art'), \
                patch.object(s.curses, 'color_pair', return_value=0):
            s.UI(self.app, scr)._home_heavy(self.app, self.app.pal, scr,
                                            0, 30, 0, 120)
        navs = [r['arg'] for r in self.app.rects if r['act'] == 'nav']
        self.assertIn("stats", navs)


class FmtAgoTests(unittest.TestCase):
    def test_buckets(self):
        import time as _t
        now = _t.time()
        self.assertEqual(s.fmt_ago(now - 300), "5m")
        self.assertEqual(s.fmt_ago(now - 7200), "2h")
        self.assertEqual(s.fmt_ago(now - 3 * 86400), "3d")
        self.assertEqual(s.fmt_ago(now - 14 * 86400), "2w")
        self.assertEqual(s.fmt_ago(now - 60), "1m")

    def test_invalid(self):
        self.assertEqual(s.fmt_ago(None), "")
        self.assertEqual(s.fmt_ago("x"), "")
        self.assertEqual(s.fmt_ago(float("nan")), "")
        self.assertEqual(s.fmt_ago(-5), "")


class MilestoneTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for name, value in [('CFG', root), ('STORE', root / 'library.json')]:
            p = patch.object(s, name, value)
            p.start()
            self.addCleanup(p.stop)
        tp = patch.object(s.threading.Thread, 'start')
        tp.start()
        self.addCleanup(tp.stop)
        self.app = s.App()
        self.app.toast_now = Mock()
        self.app.snapshot_session = Mock()
        self.app.refresh_similar = Mock()

    def test_song_milestone(self):
        self.app.store.plays = {"1": dict(title="S1", artist="A", n=24)}
        self.app._note_history(track(1))
        args = self.app.toast_now.call_args[0][0]
        self.assertIn("25 plays!", args)

    def test_total_milestone(self):
        self.app.store.plays = {"1": dict(title="S1", artist="A", n=490),
                                "2": dict(title="S2", artist="B", n=9)}
        self.app._note_history(track(2))
        args = self.app.toast_now.call_args[0][0]
        self.assertIn("500 plays on SpotUI!", args)

    def test_no_milestone(self):
        self.app.store.plays = {"1": dict(title="S1", artist="A", n=10)}
        self.app._note_history(track(1))
        self.app.toast_now.assert_not_called()


class StatsWeekTopTests(unittest.TestCase):
    def test_top_artist_this_week(self):
        import time as _t
        store = s.Store()
        now = _t.time()
        store.history = [
            dict(track(1), artist="Luna Waves", added=now - 3600),
            dict(track(2), artist="Luna Waves", added=now - 7200),
            dict(track(3), artist="Neon Coast", added=now - 1800),
            dict(track(4), artist="Neon Coast", added=now - 8 * 86400),
        ]
        self.assertEqual(s.stats_week_top(store), ("Luna Waves", 2))

    def test_empty(self):
        store = s.Store()
        store.history = [dict(track(1), artist="", added=1e12)]
        self.assertEqual(s.stats_week_top(store), ("", 0))


class ArtistMinutesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for name, value in [('CFG', root), ('STORE', root / 'library.json')]:
            p = patch.object(s, name, value)
            p.start()
            self.addCleanup(p.stop)
        tp = patch.object(s.threading.Thread, 'start')
        tp.start()
        self.addCleanup(tp.stop)
        self.app = s.App()

    def test_minutes_sum(self):
        self.app.store.liked = [dict(track(1), dur=200),
                                dict(track(2), dur=100)]
        self.app.store.plays = {
            "1": dict(title="S1", artist="Luna Waves", n=9),   # 30 min
            "2": dict(title="S2", artist="Luna Waves", n=3),   # 5 min
            "3": dict(title="S3", artist="Other", n=50),       # no dur
        }
        self.assertEqual(self.app.artist_minutes("Luna Waves"), "35 min")
        self.assertEqual(self.app.artist_minutes("Other"), "")

    def test_hours_format(self):
        self.app.store.liked = [dict(track(1), dur=240)]
        self.app.store.plays = {
            "1": dict(title="S1", artist="Luna Waves", n=31),  # 124 min
        }
        self.assertEqual(self.app.artist_minutes("luna waves"),
                         "2 hr 4 min")


class SleepFadeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for name, value in [('CFG', root), ('STORE', root / 'library.json')]:
            p = patch.object(s, name, value)
            p.start()
            self.addCleanup(p.stop)
        tp = patch.object(s.threading.Thread, 'start')
        tp.start()
        self.addCleanup(tp.stop)
        self.app = s.App()
        self.app.mpv.cmd = Mock()
        self.app.mpv.state["vol"] = 70

    def test_timed_fade_ramps_volume(self):
        import time as _t
        self.app.sleep_deadline = _t.monotonic() + 10
        self.app._sleep_fade()
        self.app.mpv.cmd.assert_called_with(
            ["set_property", "volume", 35])
        self.assertTrue(self.app._fading)

    def test_fade_restores_when_disarmed(self):
        self.app._fading = True
        self.app._fade_level = 35
        self.app._sleep_fade()          # no timer armed
        self.app.mpv.cmd.assert_called_with(
            ["set_property", "volume", 70])
        self.assertFalse(self.app._fading)

    def test_eot_fade_uses_track_time_left(self):
        self.app.sleep_eot = True
        self.app.mpv.state.update(idle=False, pos=190.0, dur=200.0)
        self.app._sleep_fade()
        self.app.mpv.cmd.assert_called_with(
            ["set_property", "volume", 35])

    def test_no_timer_no_call(self):
        self.app._sleep_fade()
        self.app.mpv.cmd.assert_not_called()
        self.assertFalse(self.app._fading)


class HomeTileCountsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for name, value in [('CFG', root), ('STORE', root / 'library.json')]:
            p = patch.object(s, name, value)
            p.start()
            self.addCleanup(p.stop)
        tp = patch.object(s.threading.Thread, 'start')
        tp.start()
        self.addCleanup(tp.stop)
        self.app = s.App()
        self.app.refresh_similar = Mock()

    def test_tiles_show_counts_and_minutes(self):
        from collections import defaultdict
        self.app.store.liked = [dict(track(1), dur=120),
                                dict(track(2), dur=180)]
        self.app.store.playlists = [
            {"name": "Gym", "tracks": [dict(track(3), dur=600)]}]
        self.app.pal = defaultdict(int)
        self.app.cover_for = Mock(return_value=None)
        scr = Mock()
        scr.getmaxyx.return_value = (40, 140)
        ui = s.UI(self.app, scr)
        ui.hint = Mock()
        texts = []
        with patch.object(s, 'put',
                          side_effect=lambda sc, y, x, t, *a, **k:
                          texts.append(str(t))), \
                patch.object(s, 'draw_art'):
            ui._home_tiles(self.app, self.app.pal, scr, 0, 30, 24, 120)
        self.assertIn("2 songs \u00b7 5 min", texts)
        self.assertIn("1 song \u00b7 10 min", texts)


class StatsOnRepeatTests(unittest.TestCase):
    def test_counts_repeats_in_week(self):
        import time as _t
        store = s.Store()
        now = _t.time()
        store.history = (
            [dict(track(1), added=now - 3600 * i) for i in range(3)]
            + [dict(track(2), added=now - 7200 * i) for i in range(2)]
            + [dict(track(3), added=now)]
            + [dict(track(1), added=now - 9 * 86400)]   # outside window
        )
        rows = s.stats_on_repeat(store)
        self.assertEqual([(t["id"], n) for t, n in rows],
                         [("1", 3), ("2", 2)])

    def test_bad_entries_ignored(self):
        store = s.Store()
        store.history = [None, {"added": "x"}, {"id": None, "added": 1}]
        self.assertEqual(s.stats_on_repeat(store), [])


class QueueSourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for name, value in [('CFG', root), ('STORE', root / 'library.json')]:
            p = patch.object(s, name, value)
            p.start()
            self.addCleanup(p.stop)
        tp = patch.object(s.threading.Thread, 'start')
        tp.start()
        self.addCleanup(tp.stop)
        self.app = s.App()

    def test_play_stamps_source(self):
        self.app.play([dict(track(1)), dict(track(2))], 0,
                      source="Late Night Drive")
        self.assertEqual([t.get("src") for t in self.app.queue],
                         ["Late Night Drive", "Late Night Drive"])

    def test_manual_adds_marked_added(self):
        self.app.play([dict(track(1))], 0, source="Mix")
        self.app.add_queue(dict(track(2)))
        self.app.play_next(dict(track(3)))
        self.assertEqual(self.app.queue[1].get("src"), "Added")
        self.assertEqual(self.app.queue[2].get("src"), "Added")
        self.assertEqual(self.app.queue[0].get("src"), "Mix")

    def test_no_source_no_stamp(self):
        self.app.play([dict(track(1))], 0)
        self.assertNotIn("src", self.app.queue[0])


class HistoryDedupeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for name, value in [('CFG', root), ('STORE', root / 'library.json')]:
            p = patch.object(s, name, value)
            p.start()
            self.addCleanup(p.stop)
        tp = patch.object(s.threading.Thread, 'start')
        tp.start()
        self.addCleanup(tp.stop)
        self.app = s.App()

    def test_dedupe_keeps_newest_first(self):
        self.app.store.history = [dict(track(1)), dict(track(2)),
                                  dict(track(1)), dict(track(3))]
        self.app.stack = [("home", None), ("history", None)]
        self.assertEqual([t["id"] for t in self.app.view_tracks()],
                         ["1", "2", "1", "3"])
        self.app.store.hist_dedupe = True
        self.assertEqual([t["id"] for t in self.app.view_tracks()],
                         ["1", "2", "3"])

    def test_dedupe_persists(self):
        self.app.store.hist_dedupe = True
        self.app.store.save()
        st = s.Store()
        self.assertTrue(st.hist_dedupe)


class StatsDayMinutesTests(unittest.TestCase):
    def test_minutes_per_day(self):
        import time as _t
        store = s.Store()
        # anchor on local midnight: relative "now - Nh" anchors flake when
        # the run crosses midnight, since the buckets are calendar days
        lt = _t.localtime()
        today0 = _t.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday,
                            0, 0, 0, 0, 0, -1))
        store.history = [
            {"id": "1", "added": today0 + 3600, "dur": 180},      # today 3m
            {"id": "2", "added": today0 + 3600, "dur": 120},      # today +2m
            {"id": "3", "added": today0 - 3600, "dur": 600},      # yesterday 10m
            {"id": "4", "added": today0 - 8 * 86400, "dur": 300}, # outside
            {"id": "5", "added": today0 + 3600},                  # no dur
        ]
        mins = s.stats_day_minutes(store)
        self.assertEqual(len(mins), 7)
        self.assertEqual(mins[-1], 5)
        self.assertEqual(mins[-2], 10)
        self.assertEqual(sum(mins), 15)

    def test_bad_entries_ignored(self):
        store = s.Store()
        store.history = [None, {"added": "x", "dur": "y"},
                         {"added": float("nan"), "dur": 60}]
        self.assertEqual(s.stats_day_minutes(store), [0] * 7)


class NowPlayingMoreFromTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for name, value in [('CFG', root), ('STORE', root / 'library.json')]:
            p = patch.object(s, name, value)
            p.start()
            self.addCleanup(p.stop)
        tp = patch.object(s.threading.Thread, 'start')
        tp.start()
        self.addCleanup(tp.stop)
        self.app = s.App()
        self.app.refresh_similar = Mock()

    def test_wide_now_playing_lists_more_from_artist(self):
        from collections import defaultdict
        self.app.queue = [dict(track(1), artist="Luna Waves")]
        self.app.qpos = 0
        self.app.current = self.app.queue[0]
        self.app.mpv.state.update(pos=74.0, dur=200.0, idle=False)
        self.app.store.liked = [dict(track(2), artist="Luna Waves"),
                                dict(track(3), artist="Luna Waves"),
                                dict(track(4), artist="Other")]
        self.app.store.plays = {"2": dict(title="S2", artist="Luna Waves",
                                          n=9),
                                "3": dict(title="S3", artist="Luna Waves",
                                          n=4)}
        self.app.pal = defaultdict(int)
        self.app.cover_for = Mock(return_value=None)
        scr = Mock()
        scr.getmaxyx.return_value = (40, 140)
        ui = s.UI(self.app, scr)
        ui.hint = Mock()
        self.app.rects = []
        texts = []
        with patch.object(s, 'put',
                          side_effect=lambda sc, y, x, t, *a, **k:
                          texts.append(str(t))), \
                patch.object(s, 'draw_art'):
            ui.v_playing(0, 34, 24, 120)
        self.assertIn("MORE FROM LUNA WAVES", texts)
        hits = [r for r in self.app.rects if r["act"] == "playtrack"]
        self.assertEqual([r["arg"][0]["id"] for r in hits], ["2", "3"])
        self.assertEqual(hits[0]["arg"][1], "Luna Waves")


class SleepEndOfTrackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for name, value in [('CFG', root), ('STORE', root / 'library.json')]:
            p = patch.object(s, name, value)
            p.start()
            self.addCleanup(p.stop)
        tp = patch.object(s.threading.Thread, 'start')
        tp.start()
        self.addCleanup(tp.stop)
        self.app = s.App()
        self.app.refresh_similar = Mock()

    def test_cycle_reaches_end_of_track_then_off(self):
        seen = []
        for _ in range(7):
            self.app.cycle_sleep()
            seen.append("eot" if self.app.sleep_eot
                        else self.app.sleep_minutes)
        # the 6th press opens the custom prompt and leaves the timer at
        # eot; the 7th moves on to off
        self.assertEqual(seen, [15, 30, 60, 90, "eot", "eot", 0])
        self.assertIsNone(self.app.sleep_deadline)

    def test_custom_cancel_then_cycle_goes_off(self):
        for _ in range(5):
            self.app.cycle_sleep()
        self.assertTrue(self.app.sleep_eot)
        self.app.cycle_sleep()                     # custom prompt opens
        self.assertEqual(self.app.mode, "sleep")
        s.handle_key(self.app, "\x1b")            # cancel
        self.app.cycle_sleep()                     # moves on, not stuck
        self.assertEqual(self.app.mode, "normal")
        self.assertIsNone(self.app.sleep_deadline)
        self.assertEqual(self.app.sleep_minutes, 0)

    def test_end_of_track_pauses_instead_of_advancing(self):
        self.app.queue = [track(1), track(2)]
        self.app.qpos = 0
        self.app.current = self.app.queue[0]
        self.app.sleep_eot = True
        self.app.next = Mock()
        self.app.mpv.cmd = Mock()
        self.app._track_ended()
        self.app.next.assert_not_called()
        self.assertFalse(self.app.sleep_eot)
        self.assertTrue(self.app.mpv.state["pause"])
        self.app.mpv.cmd.assert_called_once_with(
            ["set_property", "pause", True])

    def test_normal_end_advances(self):
        self.app.queue = [track(1), track(2)]
        self.app.qpos = 0
        self.app.current = self.app.queue[0]
        self.app.next = Mock()
        self.app._track_ended()
        self.app.next.assert_called_once_with(auto=True)


class SearchPlayCountTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for name, value in [('CFG', root), ('STORE', root / 'library.json')]:
            p = patch.object(s, name, value)
            p.start()
            self.addCleanup(p.stop)
        tp = patch.object(s.threading.Thread, 'start')
        tp.start()
        self.addCleanup(tp.stop)
        self.app = s.App()
        self.app.refresh_similar = Mock()

    def _row_texts(self, vk):
        from collections import defaultdict
        self.app.pal = defaultdict(int)
        scr = Mock()
        scr.getmaxyx.return_value = (40, 140)
        ui = s.UI(self.app, scr)
        self.app.rects = []
        texts = []
        with patch.object(s, 'put',
                          side_effect=lambda sc, y, x, t, *a, **k:
                          texts.append(str(t))):
            ui.row(3, 24, 86, dict(track(1), artist="Luna Waves"),
                   0, vk, 0, show_date=False)
        return texts

    def test_search_rows_show_play_count(self):
        self.app.store.plays = {"1": dict(title="S", artist="A", n=45)}
        self.assertIn(" \u00b7 45 plays", self._row_texts("search:"))

    def test_other_lists_stay_quiet(self):
        self.app.store.plays = {"1": dict(title="S", artist="A", n=45)}
        texts = self._row_texts("liked:")
        self.assertNotIn("\u00b7 45 plays", texts)

    def test_unplayed_songs_show_nothing(self):
        self.app.store.plays = {}
        texts = self._row_texts("search:")
        self.assertNotIn("\u00b7 0 plays", texts)


class JumpBackInTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for name, value in [('CFG', root), ('STORE', root / 'library.json')]:
            p = patch.object(s, name, value)
            p.start()
            self.addCleanup(p.stop)
        tp = patch.object(s.threading.Thread, 'start')
        tp.start()
        self.addCleanup(tp.stop)
        self.app = s.App()
        self.app.refresh_similar = Mock()

    def _render(self):
        from collections import defaultdict
        self.app.pal = defaultdict(int)
        self.app.query = ""
        self.app.searching = False
        scr = Mock()
        scr.getmaxyx.return_value = (40, 120)
        ui = s.UI(self.app, scr)
        ui.hint = Mock()
        self.app.rects = []
        texts = []
        with patch.object(s, 'put',
                          side_effect=lambda sc, y, x, t, *a, **k:
                          texts.append(str(t))), \
                patch.object(s, 'draw_art'):
            ui.v_search(0, 34, 24, 120)
        return texts

    def test_empty_search_offers_jump_back_in(self):
        self.app.store.recent = ["midnight"]
        self.app.store.history = [dict(track(1), added=100.0),
                                  dict(track(2), added=90.0)]
        texts = self._render()
        self.assertIn("Jump back in", texts)
        self.assertIn("Song 1", texts)
        hits = [r for r in self.app.rects if r["act"] == "playtrack"]
        self.assertEqual(len(hits), 2)
        trk, source = hits[0]["arg"]
        self.assertEqual(trk["id"], "1")
        self.assertEqual(source, "Jump back in")
        self.app.play = Mock()
        with patch.object(s.curses, 'getmouse',
                          return_value=(0, hits[0]["x0"] + 1, hits[0]["y0"],
                                        0, s.curses.BUTTON1_CLICKED)):
            s.handle_mouse(self.app)
        self.app.play.assert_called_once()
        self.assertEqual(self.app.play.call_args[1]["source"],
                         "Jump back in")

    def test_no_jump_back_in_without_history(self):
        self.app.store.recent = ["midnight"]
        self.app.store.history = []
        texts = self._render()
        self.assertNotIn("Jump back in", texts)


class QueueRemainingTests(unittest.TestCase):
    def test_fmt_remaining(self):
        self.assertEqual(s.fmt_remaining([]), "")
        self.assertEqual(s.fmt_remaining([dict(dur=None)]), "")
        self.assertEqual(s.fmt_remaining([dict(dur=90), dict(dur=90)]),
                         "3 min left")
        self.assertEqual(s.fmt_remaining([dict(dur=4000)]), "1 hr 6 min left")


class ViewHintTests(unittest.TestCase):
    def test_every_main_view_has_a_hint_with_real_keys(self):
        for kind in ("search", "liked", "playlist", "history", "artist",
                     "queue", "playing", "stats"):
            hint = s.VIEW_HINTS.get(kind)
            self.assertTrue(hint, kind)
            self.assertIn("\u00b7", hint)      # at least two tips

    def test_hint_text_mentions_existing_keys(self):
        # guard against hints drifting from the key map
        joined = " ".join(s.VIEW_HINTS.values())
        for key in ("Enter", "a", "F", "o", "J/K", "C", "W", "Space", "s", "r"):
            self.assertIn(key, joined)


class MouseDragTests(unittest.TestCase):
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

    def test_drag_motion_updates_volume(self):
        self.app.drag_rect = {"act": "vol", "arg": (0, 10)}
        with patch.object(s.curses, 'getmouse',
                          return_value=(0, 4, 5, 0, s.curses.REPORT_MOUSE_POSITION)):
            s.handle_mouse(self.app)
        self.assertEqual(self.app.mpv.state["vol"], 44)  # 4/9 of the slider

    def test_release_ends_drag(self):
        self.app.drag_rect = {"act": "vol", "arg": (0, 10)}
        with patch.object(s.curses, 'getmouse',
                          return_value=(0, 9, 5, 0, s.curses.BUTTON1_RELEASED
                                        | s.curses.REPORT_MOUSE_POSITION)):
            s.handle_mouse(self.app)
        self.assertIsNone(self.app.drag_rect)
        self.assertEqual(self.app.mpv.state["vol"], 100)

    def test_mouse_tracking_sequence(self):
        import io
        with patch.object(s.sys, "stdout", io.StringIO()) as buf:
            s.mouse_tracking(True)
            s.mouse_tracking(False)
        out = buf.getvalue()
        self.assertIn("\x1b[?1002h", out)
        self.assertIn("\x1b[?1006h", out)
        self.assertNotIn("1003", out)          # 1003 wedges some ncurses builds
        self.assertIn("\x1b[?1002l", out)


if __name__ == '__main__':
    unittest.main()


class SortTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for name, value in [('CFG', root), ('STORE', root / 'library.json')]:
            p = patch.object(s, name, value)
            p.start()
            self.addCleanup(p.stop)
        tp = patch.object(s.threading.Thread, 'start')
        tp.start()
        self.addCleanup(tp.stop)
        self.app = s.App()
        self.app.refresh_similar = Mock()
        self.app.store.liked = [
            {"id": "b", "title": "Bravo", "artist": "Yara", "dur": 100,
             "added": 200},
            {"id": "a", "title": "alpha", "artist": "Zed", "dur": 300,
             "added": 100},
            {"id": "c", "title": "Charlie", "artist": "Xena", "dur": 200,
             "added": 300},
        ]

    def _ids(self):
        return [t["id"] for t in self.app.view_tracks("liked:")]

    def test_default_keeps_store_order(self):
        self.assertEqual(self.app.store.sort_mode, "default")
        self.assertEqual(self._ids(), ["b", "a", "c"])

    def test_title_sort_is_case_insensitive_copy(self):
        self.app.store.sort_mode = "title"
        self.assertEqual(self._ids(), ["a", "b", "c"])
        # stored order untouched
        self.assertEqual([t["id"] for t in self.app.store.liked],
                         ["b", "a", "c"])

    def test_artist_added_and_dur_sorts(self):
        self.app.store.sort_mode = "artist"
        self.assertEqual(self._ids(), ["c", "b", "a"])   # Xena, Yara, Zed
        self.app.store.sort_mode = "added"
        self.assertEqual(self._ids(), ["c", "b", "a"])   # newest first
        self.app.store.sort_mode = "dur"
        self.assertEqual(self._ids(), ["a", "c", "b"])   # longest first

    def test_cycle_sort_rotates_and_saves(self):
        seen = []
        for _ in range(len(s.SORT_MODES)):
            seen.append(self.app.store.sort_mode)
            self.app.cycle_sort()
        self.assertEqual(seen, list(s.SORT_MODES))
        self.assertEqual(self.app.store.sort_mode, "default")

    def test_set_sort_click_toggles_back_to_default(self):
        self.app.set_sort("title")
        self.assertEqual(self.app.store.sort_mode, "title")
        self.app.set_sort("title")          # second click restores order
        self.assertEqual(self.app.store.sort_mode, "default")

    def test_delete_selected_removes_the_sorted_row_not_the_store_row(self):
        self.app.store.sort_mode = "title"
        self.app.store.playlists = [
            {"name": "P", "tracks": [dict(t) for t in self.app.store.liked]}]
        self.app.stack.append(("playlist", 0))
        self.app.sel["playlist:0"] = 0      # 'alpha' under title sort
        self.app.delete_selected()
        remaining = [t["id"] for t in self.app.store.playlists[0]["tracks"]]
        self.assertEqual(remaining, ["b", "c"])

    def test_sort_mode_persists(self):
        self.app.store.sort_mode = "artist"
        self.app.store.save()
        fresh = s.Store()
        self.assertEqual(fresh.sort_mode, "artist")

    def test_queue_and_search_ignore_sort(self):
        self.app.store.sort_mode = "title"
        self.app.queue = list(reversed(self.app.store.liked))
        self.assertEqual([t["id"] for t in self.app.view_tracks("queue:")],
                         ["c", "a", "b"])


class QueueDragTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for name, value in [('CFG', root), ('STORE', root / 'library.json')]:
            p = patch.object(s, name, value)
            p.start()
            self.addCleanup(p.stop)
        tp = patch.object(s.threading.Thread, 'start')
        tp.start()
        self.addCleanup(tp.stop)
        self.app = s.App()
        self.app.refresh_similar = Mock()
        self.app.queue = [{"id": str(i), "title": f"T{i}", "artist": "A",
                           "dur": 60} for i in range(5)]
        self.app.qpos = 0

    @staticmethod
    def _row(y, idx):
        return {"x0": 0, "x1": 20, "y0": y, "y1": y + 1,
                "act": "row", "arg": ("queue:", idx, False)}

    def _mouse(self, x, y, bstate):
        with patch.object(s.curses, 'getmouse',
                          return_value=(0, x, y, 0, bstate)):
            s.handle_mouse(self.app)

    def test_press_on_upcoming_row_starts_drag(self):
        self.app.rects = [self._row(2, 2)]
        self._mouse(5, 2, s.curses.BUTTON1_PRESSED)
        self.assertEqual(self.app.drag_row, ["queue:", 2])

    def test_press_on_now_playing_row_does_not_drag(self):
        self.app.rects = [self._row(1, 0)]       # idx == qpos
        self._mouse(5, 1, s.curses.BUTTON1_PRESSED)
        self.assertIsNone(self.app.drag_row)

    def test_motion_reorders_live(self):
        self.app.drag_row = ["queue:", 2]
        self.app.rects = [self._row(4, 4)]
        self._mouse(5, 4, s.curses.REPORT_MOUSE_POSITION)
        self.assertEqual([t["id"] for t in self.app.queue],
                         ["0", "1", "3", "4", "2"])
        self.assertEqual(self.app.drag_row, ["queue:", 4])
        # selection follows the dragged song
        self.assertEqual(self.app.sel.get("queue:"), 4)

    def test_motion_cannot_cross_now_playing(self):
        self.app.drag_row = ["queue:", 2]
        self.app.rects = [self._row(1, 0)]
        self._mouse(5, 1, s.curses.REPORT_MOUSE_POSITION)
        self.assertEqual([t["id"] for t in self.app.queue][0], "0")
        self.assertEqual(self.app.drag_row, ["queue:", 1])  # stops after qpos

    def test_release_ends_queue_drag(self):
        self.app.drag_row = ["queue:", 3]
        self.app.rects = []
        self._mouse(5, 9, s.curses.BUTTON1_RELEASED
                    | s.curses.REPORT_MOUSE_POSITION)
        self.assertIsNone(self.app.drag_row)


class PlaylistDragTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for name, value in [('CFG', root), ('STORE', root / 'library.json')]:
            p = patch.object(s, name, value)
            p.start()
            self.addCleanup(p.stop)
        tp = patch.object(s.threading.Thread, 'start')
        tp.start()
        self.addCleanup(tp.stop)
        self.app = s.App()
        self.app.refresh_similar = Mock()
        self.app.store.playlists = [{"name": "P", "tracks": [
            {"id": c, "title": c, "artist": "A", "dur": 60}
            for c in "abcd"]}]
        self.app.stack.append(("playlist", 0))

    @staticmethod
    def _row(y, idx):
        return {"x0": 0, "x1": 20, "y0": y, "y1": y + 1,
                "act": "row", "arg": ("playlist:0", idx, False)}

    def _mouse(self, x, y, bstate):
        with patch.object(s.curses, 'getmouse',
                          return_value=(0, x, y, 0, bstate)):
            s.handle_mouse(self.app)

    def _ids(self):
        return [t["id"] for t in self.app.store.playlists[0]["tracks"]]

    def test_press_starts_playlist_drag(self):
        self.app.rects = [self._row(2, 1)]
        self._mouse(5, 2, s.curses.BUTTON1_PRESSED)
        self.assertEqual(self.app.drag_row, ["playlist:0", 1])

    def test_motion_reorders_playlist_live(self):
        self.app.drag_row = ["playlist:0", 0]
        self.app.rects = [self._row(5, 2)]
        self._mouse(5, 5, s.curses.REPORT_MOUSE_POSITION)
        self.assertEqual(self._ids(), ["b", "c", "a", "d"])
        self.assertEqual(self.app.drag_row, ["playlist:0", 2])

    def test_no_drag_while_sorted(self):
        self.app.store.sort_mode = "title"
        self.app.rects = [self._row(2, 1)]
        self._mouse(5, 2, s.curses.BUTTON1_PRESSED)
        self.assertIsNone(self.app.drag_row)
        self.assertEqual(self._ids(), ["a", "b", "c", "d"])

    def test_queue_drag_ignores_playlist_rects(self):
        # a queue drag hovering a playlist rect must not crash or reorder
        self.app.queue = [{"id": str(i), "title": "t", "artist": "a",
                           "dur": 1} for i in range(3)]
        self.app.qpos = 0
        self.app.drag_row = ["queue:", 1]
        self.app.rects = [self._row(3, 0)]
        self._mouse(5, 3, s.curses.REPORT_MOUSE_POSITION)
        self.assertEqual([t["id"] for t in self.app.queue], ["0", "1", "2"])


class PlaylistReorderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for name, value in [('CFG', root), ('STORE', root / 'library.json')]:
            p = patch.object(s, name, value)
            p.start()
            self.addCleanup(p.stop)
        tp = patch.object(s.threading.Thread, 'start')
        tp.start()
        self.addCleanup(tp.stop)
        self.app = s.App()
        self.app.refresh_similar = Mock()
        self.app.store.playlists = [{"name": "P", "tracks": [
            {"id": c, "title": c, "artist": "A", "dur": 60}
            for c in "abcd"]}]
        self.app.stack.append(("playlist", 0))

    def _ids(self):
        return [t["id"] for t in self.app.store.playlists[0]["tracks"]]

    def test_j_moves_down_and_selection_follows(self):
        self.app.sel["playlist:0"] = 1
        s.handle_key(self.app, "J")
        self.assertEqual(self._ids(), ["a", "c", "b", "d"])
        self.assertEqual(self.app.sel["playlist:0"], 2)

    def test_k_moves_up(self):
        self.app.sel["playlist:0"] = 2
        s.handle_key(self.app, "K")
        self.assertEqual(self._ids(), ["a", "c", "b", "d"])

    def test_edges_do_nothing(self):
        self.app.sel["playlist:0"] = 0
        s.handle_key(self.app, "K")
        self.assertEqual(self._ids(), ["a", "b", "c", "d"])
        self.app.sel["playlist:0"] = 3
        s.handle_key(self.app, "J")
        self.assertEqual(self._ids(), ["a", "b", "c", "d"])

    def test_reorder_persists(self):
        self.app.sel["playlist:0"] = 0
        s.handle_key(self.app, "J")
        fresh = s.Store()
        self.assertEqual([t["id"] for t in fresh.playlists[0]["tracks"]],
                         ["b", "a", "c", "d"])

    def test_blocked_while_sorted(self):
        self.app.store.sort_mode = "title"
        self.app.sel["playlist:0"] = 1
        s.handle_key(self.app, "J")
        self.assertEqual(self._ids(), ["a", "b", "c", "d"])
        self.assertIn("sort", self.app.toast[0])


class QJumpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for name, value in [('CFG', root), ('STORE', root / 'library.json')]:
            p = patch.object(s, name, value)
            p.start()
            self.addCleanup(p.stop)
        tp = patch.object(s.threading.Thread, 'start')
        tp.start()
        self.addCleanup(tp.stop)
        self.app = s.App()
        self.app.refresh_similar = Mock()
        self.app.queue = [{"id": str(i), "title": f"T{i}", "artist": "A",
                           "dur": 60} for i in range(4)]
        self.app.qpos = 0
        self.app.current = self.app.queue[0]

    def _mouse(self, x, y, bstate):
        with patch.object(s.curses, 'getmouse',
                          return_value=(0, x, y, 0, bstate)):
            s.handle_mouse(self.app)

    def test_click_jumps_to_that_song(self):
        self.app.rects = [{"x0": 0, "x1": 40, "y0": 3, "y1": 4,
                           "act": "qjump", "arg": 2}]
        self._mouse(5, 3, s.curses.BUTTON1_PRESSED)
        self.assertEqual(self.app.qpos, 2)
        self.assertEqual(self.app.current["id"], "2")

    def test_click_current_song_is_a_noop(self):
        self.app.rects = [{"x0": 0, "x1": 40, "y0": 3, "y1": 4,
                           "act": "qjump", "arg": 0}]
        self._mouse(5, 3, s.curses.BUTTON1_PRESSED)
        self.assertEqual(self.app.qpos, 0)
        self.assertFalse(self.app.loading)

    def test_out_of_range_ignored(self):
        self.app.rects = [{"x0": 0, "x1": 40, "y0": 3, "y1": 4,
                           "act": "qjump", "arg": 9}]
        self._mouse(5, 3, s.curses.BUTTON1_PRESSED)
        self.assertEqual(self.app.qpos, 0)


class StatsMinutesTests(unittest.TestCase):
    def _store(self):
        st = s.Store.__new__(s.Store)     # bare store, no disk
        st.liked = [{"id": "a", "title": "A", "artist": "X", "dur": 200},
                    {"id": "b", "title": "B", "artist": "Y", "dur": 100}]
        st.history = [{"id": "c", "title": "C", "artist": "Z", "dur": 60}]
        st.playlists = []
        return st

    def test_sums_known_durations(self):
        st = self._store()
        st.plays = {"a": {"title": "A", "artist": "X", "n": 3},     # 600s
                    "c": {"title": "C", "artist": "Z", "n": 2},     # 120s
                    "zz": {"title": "?", "artist": "?", "n": 50}}   # no dur
        # 720s = 12 min
        self.assertEqual(s.stats_minutes(st), "12 min")

    def test_hours_format(self):
        st = self._store()
        st.plays = {"a": {"title": "A", "artist": "X", "n": 18}}    # 60 min
        self.assertEqual(s.stats_minutes(st), "1 hr 0 min")

    def test_under_a_minute_is_empty(self):
        st = self._store()
        st.plays = {"b": {"title": "B", "artist": "Y", "n": 0}} or {}
        st.plays = {}
        self.assertEqual(s.stats_minutes(st), "")


class StatsHoursTests(unittest.TestCase):
    def _at(self, hour, minute=0):
        lt = s.time.localtime()
        return s.time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday,
                              hour, minute, 0, 0, 0, -1))

    def _store(self, hours):
        st = s.Store.__new__(s.Store)     # bare store, no disk
        st.history = [{"id": str(i), "added": self._at(h)}
                      for i, h in enumerate(hours)]
        return st

    def test_buckets(self):
        st = self._store([8, 11, 13, 19, 21, 23, 2])
        self.assertEqual(s.stats_hours(st),
                         [("Morning", 2), ("Afternoon", 1),
                          ("Evening", 2), ("Night", 2)])

    def test_ignores_bad_timestamps(self):
        st = self._store([10])
        st.history += [{"id": "x"}, {"id": "y", "added": "soon"},
                       {"id": "z", "added": float("nan")}]
        self.assertEqual(s.stats_hours(st),
                         [("Morning", 1), ("Afternoon", 0),
                          ("Evening", 0), ("Night", 0)])


class StatsStreakTests(unittest.TestCase):
    def _store(self, days_ago):
        st = s.Store.__new__(s.Store)     # bare store, no disk
        now = s.time.time()
        st.history = [{"id": str(i), "added": now - d * 86400}
                      for i, d in enumerate(days_ago)]
        return st

    def test_consecutive_days_ending_today(self):
        self.assertEqual(s.stats_streak(self._store([0, 1, 2, 4])), 3)

    def test_streak_may_end_yesterday(self):
        self.assertEqual(s.stats_streak(self._store([1, 2])), 2)

    def test_older_last_play_breaks_the_streak(self):
        self.assertEqual(s.stats_streak(self._store([2, 3])), 0)
        self.assertEqual(s.stats_streak(self._store([])), 0)


class StatsLastPlayedTests(unittest.TestCase):
    def _store(self, rows):
        st = s.Store.__new__(s.Store)     # bare store, no disk
        st.history = rows
        return st

    def test_latest_epoch_wins(self):
        st = self._store([{"id": "1", "added": 100.0},
                          {"id": "1", "added": 250.0},
                          {"id": "2", "added": 90.0}])
        self.assertEqual(s.stats_last_played(st), {"1": 250.0, "2": 90.0})

    def test_ignores_bad_rows(self):
        st = self._store([{"id": "1", "added": 100.0},
                          {"added": 500.0},
                          {"id": "2", "added": "soon"},
                          {"id": "3", "added": float("nan")},
                          "junk"])
        self.assertEqual(s.stats_last_played(st), {"1": 100.0})


class StatsWeekdayTests(unittest.TestCase):
    def _store(self, stamps):
        st = s.Store.__new__(s.Store)     # bare store, no disk
        st.history = [{"id": str(i), "added": t}
                      for i, t in enumerate(stamps)]
        return st

    def _on(self, y, m, d, n):
        # n plays at local noon on the given date
        t = s.time.mktime((y, m, d, 12, 0, 0, 0, 0, -1))
        return [t] * n

    def test_busiest_weekday(self):
        # 2026-11-07 is a Saturday, 2026-11-11 a Wednesday
        st = self._store(self._on(2026, 11, 7, 12)
                         + self._on(2026, 11, 11, 5))
        self.assertEqual(s.stats_weekday(st), ("Saturdays", 12))

    def test_thin_history_says_nothing(self):
        st = self._store(self._on(2026, 11, 7, 9))
        self.assertIsNone(s.stats_weekday(st))

    def test_tie_says_nothing(self):
        st = self._store(self._on(2026, 11, 7, 6)
                         + self._on(2026, 11, 11, 6))
        self.assertIsNone(s.stats_weekday(st))

    def test_ignores_bad_timestamps(self):
        st = self._store(self._on(2026, 11, 7, 12))
        st.history += [{"id": "x"}, {"id": "y", "added": "soon"},
                       {"id": "z", "added": float("nan")}]
        self.assertEqual(s.stats_weekday(st), ("Saturdays", 12))


class GTopBottomTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for name, value in [('CFG', root), ('STORE', root / 'library.json')]:
            p = patch.object(s, name, value)
            p.start()
            self.addCleanup(p.stop)
        tp = patch.object(s.threading.Thread, 'start')
        tp.start()
        self.addCleanup(tp.stop)
        self.app = s.App()
        self.app.refresh_similar = Mock()
        self.app.store.liked = [{"id": c, "title": c, "artist": "A",
                                 "dur": 60} for c in "abcde"]

    def test_g_and_g_bottom(self):
        self.app.push("liked")
        self.app.sel["liked:"] = 3
        s.handle_key(self.app, "g")
        self.assertEqual(self.app.sel["liked:"], 0)
        s.handle_key(self.app, "G")
        self.assertEqual(self.app.sel["liked:"], 4)

    def test_home_g_selects_last_tile(self):
        self.app.store.playlists = [{"name": "P", "tracks": []},
                                    {"name": "Q", "tracks": []}]
        s.handle_key(self.app, "G")
        self.assertEqual(self.app.sel["home:"], 2)
        s.handle_key(self.app, "g")
        self.assertEqual(self.app.sel["home:"], 0)

    def test_empty_list_stays_at_zero(self):
        self.app.store.liked = []
        self.app.push("liked")
        s.handle_key(self.app, "G")
        self.assertEqual(self.app.sel["liked:"], 0)


class ResumeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for name, value in [('CFG', root), ('STORE', root / 'library.json')]:
            p = patch.object(s, name, value)
            p.start()
            self.addCleanup(p.stop)
        tp = patch.object(s.threading.Thread, 'start')
        tp.start()
        self.addCleanup(tp.stop)
        self.app = s.App()
        self.app.refresh_similar = Mock()
        tr = lambda i: {"id": i, "title": i, "artist": "A", "dur": 200,
                        "url": "u"}
        self.app.queue = [tr("x"), tr("y"), tr("z")]
        self.app.qpos = 1
        self.app.store.history = [tr("y"), tr("x")]

    def test_resume_sets_pending_seek_and_plays(self):
        self.app._resume_t = 74.0
        self.app.resume_session_or_play()
        self.assertEqual(self.app.current["id"], "y")
        self.assertEqual(self.app.pending_seek,
                         (self.app.load_token, 74.0))
        self.assertTrue(self.app.loading)

    def test_resume_without_position_just_plays(self):
        self.app._resume_t = 0.0
        self.app.resume_session_or_play()
        self.assertEqual(self.app.current["id"], "y")
        self.assertIsNone(self.app.pending_seek)

    def test_mismatched_history_plays_fresh(self):
        self.app.store.history = [{"id": "other", "title": "o",
                                   "artist": "B", "dur": 1, "url": "u"}]
        self.app.resume_session_or_play()
        self.assertEqual(self.app.current["id"], "other")
        self.assertIsNone(self.app.pending_seek)

    def test_pending_seek_applied_after_load(self):
        self.app._resume_t = 42.0
        self.app.resume_session_or_play()
        tok = self.app.pending_seek[0]
        self.app.mpv.load = Mock(return_value=True)
        self.app.mpv.seek_abs = Mock()
        with patch.object(s, "HAVE_YTDL", True), \
                patch.object(s, "resolve_url", return_value="fake://s"):
            self.app._resolve_load(self.app.queue[1], tok)
        self.app.mpv.seek_abs.assert_called_once_with(42.0)
        self.assertIsNone(self.app.pending_seek)

    def test_stale_pending_seek_not_applied(self):
        self.app._resume_t = 42.0
        self.app.resume_session_or_play()
        self.app.pending_seek = (self.app.load_token + 99, 42.0)
        self.app.mpv.load = Mock(return_value=True)
        self.app.mpv.seek_abs = Mock()
        with patch.object(s, "resolve_url", return_value="fake://s"):
            self.app._resolve_load(self.app.queue[1], self.app.load_token)
        self.app.mpv.seek_abs.assert_not_called()

    def test_snapshot_saves_and_keeps_position(self):
        self.app.current = self.app.queue[1]
        self.app.mpv.state.update(idle=False, pos=88.2)
        self.app.snapshot_session()
        self.assertEqual(self.app.store.session["t"], 88.2)
        # quit with nothing playing keeps the old position
        self.app.current = None
        self.app.mpv.state.update(idle=True)
        self.app.snapshot_session()
        self.assertEqual(self.app.store.session["t"], 88.2)

    def test_restore_reads_position(self):
        self.app.store.session = {"queue": [], "pos": 0, "t": 33.5}
        self.app.queue = []
        self.app.restore_session()
        self.assertEqual(self.app._resume_t, 33.5)

class CopyLinkTests(unittest.TestCase):
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

    def test_copy_uses_clipboard_tool(self):
        calls = []
        def fake_run(cmd, **kw):
            calls.append((cmd, kw.get('input')))
            return Mock(returncode=0)
        with patch.object(s.shutil, 'which', lambda c: '/bin/' + c if c == 'termux-clipboard-set' else None), \
             patch.object(s.subprocess, 'run', fake_run):
            url = self.app.copy_link(track(7))
        self.assertEqual(url, 'https://www.youtube.com/watch?v=7')
        self.assertEqual(calls, [(['termux-clipboard-set'], b'https://www.youtube.com/watch?v=7')])
        self.assertIn('copied', self.app.toast[0])

    def test_copy_builds_url_from_id(self):
        with patch.object(s.shutil, 'which', lambda c: '/bin/' + c if c == 'pbcopy' else None), \
             patch.object(s.subprocess, 'run', Mock(returncode=0)) as run:
            t = dict(track(9))
            del t['url']
            url = self.app.copy_link(t)
        self.assertEqual(url, 'https://www.youtube.com/watch?v=9')
        self.assertEqual(run.call_args[0][0], ['pbcopy'])

    def test_copy_falls_back_to_showing_link(self):
        with patch.object(s.shutil, 'which', lambda c: None), \
             patch('builtins.open', side_effect=OSError):
            url = self.app.copy_link(track(3))
        self.assertIn(url, self.app.toast[0])

    def test_copy_no_link(self):
        self.assertIsNone(self.app.copy_link(dict(title='x', artist='y')))
        self.assertIn('No link', self.app.toast[0])

    def test_y_key_copies_selected(self):
        self.app.store.liked = [track(1), track(2)]
        self.app.push('liked')
        self.app.sel['liked:'] = 1
        self.app.copy_link = Mock()
        s.handle_key(self.app, 'Y')
        self.app.copy_link.assert_called_once()
        self.assertEqual(self.app.copy_link.call_args[0][0]['id'], '2')

    def test_y_key_falls_back_to_current(self):
        self.app.push('queue')
        self.app.current = track(5)
        self.app.copy_link = Mock()
        s.handle_key(self.app, 'Y')
        self.app.copy_link.assert_called_once_with(self.app.current)

class LibFreshTests(unittest.TestCase):
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

    def test_empty_library_is_fresh(self):
        self.assertTrue(s.lib_fresh(self.app.store))

    def test_empty_playlist_still_fresh(self):
        self.app.create_playlist('Rock')
        self.assertTrue(s.lib_fresh(self.app.store))

    def test_liked_makes_not_fresh(self):
        self.app.store.liked = [track(1)]
        self.assertFalse(s.lib_fresh(self.app.store))

    def test_history_makes_not_fresh(self):
        self.app.store.history = [track(1)]
        self.assertFalse(s.lib_fresh(self.app.store))

    def test_plays_make_not_fresh(self):
        self.app.store.plays = {'1': {'title': 't', 'artist': 'a', 'n': 1}}
        self.assertFalse(s.lib_fresh(self.app.store))

    def test_playlist_tracks_make_not_fresh(self):
        self.app.create_playlist('Rock')
        self.app.store.playlists[0]['tracks'] = [track(1)]
        self.assertFalse(s.lib_fresh(self.app.store))

class ScrollWindowTests(unittest.TestCase):
    TXT = 'abcdefghij'   # 10 cells

    def test_short_text_unchanged(self):
        self.assertEqual(s.scroll_window('abc', 6, 0), 'abc')
        self.assertEqual(s.scroll_window('abc', 6, 99), 'abc')

    def test_holds_at_start(self):
        for tick in range(6):
            self.assertEqual(s.scroll_window(self.TXT, 6, tick), 'abcdef')

    def test_scrolls_one_cell_per_tick(self):
        self.assertEqual(s.scroll_window(self.TXT, 6, 6), 'abcdef')
        self.assertEqual(s.scroll_window(self.TXT, 6, 7), 'bcdefg')
        self.assertEqual(s.scroll_window(self.TXT, 6, 8), 'cdefgh')

    def test_holds_at_end(self):
        for tick in (10, 12, 15):
            self.assertEqual(s.scroll_window(self.TXT, 6, tick), 'efghij')

    def test_wraps_back_to_start(self):
        cycle = (10 - 6) + 12
        self.assertEqual(s.scroll_window(self.TXT, 6, cycle), 'abcdef')
        self.assertEqual(s.scroll_window(self.TXT, 6, cycle + 7), 'bcdefg')

    def test_width_wider_than_text(self):
        self.assertEqual(s.scroll_window(self.TXT, 20, 5), self.TXT)

class FmtEndsTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(s.fmt_ends([]), '')
        self.assertEqual(s.fmt_ends([dict(dur=None)]), '')

    def test_too_short(self):
        self.assertEqual(s.fmt_ends([dict(dur=45)]), '')

    def test_clock_time(self):
        now = 1763000000
        got = s.fmt_ends([dict(dur=600)], now=now)
        want = 'ends ' + __import__('time').strftime('%H:%M', __import__('time').localtime(now + 600))
        self.assertEqual(got, want)

    def test_elapsed_subtracted(self):
        now = 1763000000
        got = s.fmt_ends([dict(dur=600), dict(dur=300)], elapsed=120, now=now)
        want = 'ends ' + __import__('time').strftime('%H:%M', __import__('time').localtime(now + 780))
        self.assertEqual(got, want)

    def test_elapsed_past_total(self):
        self.assertEqual(s.fmt_ends([dict(dur=90)], elapsed=200), '')

class QueueAllTests(unittest.TestCase):
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

    def test_appends_and_toasts(self):
        self.app.current = track(100)
        self.app.queue = [track(100)]
        n = self.app.queue_all([track(1), track(2), track(3)])
        self.assertEqual(n, 3)
        self.assertEqual(len(self.app.queue), 4)
        self.assertIn('3 songs', self.app.toast[0])

    def test_skips_songs_already_queued(self):
        self.app.current = track(100)
        self.app.queue = [track(100), track(2)]
        n = self.app.queue_all([track(1), track(2), track(3)])
        self.assertEqual(n, 2)
        self.assertEqual([t['id'] for t in self.app.queue], ['100', '2', '1', '3'])

    def test_all_already_queued(self):
        self.app.current = track(1)
        self.app.queue = [track(1), track(2)]
        n = self.app.queue_all([track(1), track(2)])
        self.assertEqual(n, 0)
        self.assertIn('already', self.app.toast[0])
        self.assertEqual(len(self.app.queue), 2)

    def test_nothing_playing_starts_playback(self):
        self.app.play = Mock()
        self.app.queue_all([track(1), track(2)])
        self.app.play.assert_called_once()
        self.assertEqual(len(self.app.play.call_args[0][0]), 2)

    def test_q_key_queues_results(self):
        self.app.push('search')
        self.app.results = [track(1), track(2)]
        self.app.queue_all = Mock(return_value=2)
        s.handle_key(self.app, 'Q')
        self.app.queue_all.assert_called_once_with([self.app.results[0], self.app.results[1]])

    def test_q_key_only_in_search(self):
        self.app.push('liked')
        self.app.queue_all = Mock()
        s.handle_key(self.app, 'Q')
        self.app.queue_all.assert_not_called()

class JumpToCurrentTests(unittest.TestCase):
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

    def test_selects_playing_in_list(self):
        self.app.store.liked = [track(i) for i in range(10)]
        self.app.push('liked')
        self.app.current = track(6)
        self.app.sel['liked:'] = 0
        self.app.jump_to_current()
        self.assertEqual(self.app.sel['liked:'], 6)

    def test_nothing_playing(self):
        self.app.push('liked')
        self.app.current = None
        self.app.jump_to_current()
        self.assertIn('Nothing', self.app.toast[0])

    def test_not_in_list(self):
        self.app.store.liked = [track(1)]
        self.app.push('liked')
        self.app.current = track(99)
        self.app.jump_to_current()
        self.assertIn('not in this list', self.app.toast[0])
        self.assertEqual(self.app.sel.get('liked:', 0), 0)

    def test_queue_jumps_to_next_up(self):
        self.app.queue = [track(i) for i in range(5)]
        self.app.qpos = 1
        self.app.current = track(1)
        self.app.push('queue')
        self.app.jump_to_current()
        self.assertEqual(self.app.sel['queue:'], 2)

    def test_queue_at_end_toasts(self):
        self.app.queue = [track(1)]
        self.app.qpos = 0
        self.app.current = track(1)
        self.app.push('queue')
        self.app.jump_to_current()
        self.assertIn('last', self.app.toast[0])

    def test_dot_key(self):
        self.app.store.liked = [track(i) for i in range(10)]
        self.app.push('liked')
        self.app.current = track(4)
        s.handle_key(self.app, '.')
        self.assertEqual(self.app.sel['liked:'], 4)

class OpenSourceTests(unittest.TestCase):
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

    def test_liked(self):
        self.assertTrue(self.app.open_source('Liked Songs'))
        self.assertEqual(self.app.stack[-1], ('liked', None))

    def test_history(self):
        self.assertTrue(self.app.open_source('Recently Played'))
        self.assertEqual(self.app.stack[-1], ('history', None))

    def test_similar(self):
        self.assertTrue(self.app.open_source('Made for you'))
        self.assertEqual(self.app.stack[-1], ('similar', None))

    def test_playlist_by_name(self):
        self.app.create_playlist('Rock')
        self.app.back()
        self.assertTrue(self.app.open_source('Rock'))
        self.assertEqual(self.app.stack[-1], ('playlist', 0))

    def test_artist_fallback(self):
        self.app.store.liked = [dict(track(1), artist='Solo Act')]
        self.assertTrue(self.app.open_source('Solo Act'))
        self.assertEqual(self.app.stack[-1], ('artist', 'Solo Act'))

    def test_unknown_source_toasts(self):
        depth = len(self.app.stack)
        self.assertFalse(self.app.open_source('Autoplay'))
        self.assertEqual(len(self.app.stack), depth)
        self.assertIn('No page', self.app.toast[0])

class DuplicatePlaylistTests(unittest.TestCase):
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

    def test_duplicates_tracks(self):
        self.app.create_playlist('Rock')
        self.app.back()
        self.app.store.playlists[0]['tracks'] = [track(1), track(2)]
        self.app.duplicate_playlist(0)
        self.assertEqual(len(self.app.store.playlists), 2)
        dup = self.app.store.playlists[1]
        self.assertEqual(dup['name'], 'Rock (copy)')
        self.assertEqual([t['id'] for t in dup['tracks']], ['1', '2'])
        self.assertEqual(self.app.stack[-1], ('playlist', 1))

    def test_copy_is_independent(self):
        self.app.create_playlist('Rock')
        self.app.back()
        self.app.store.playlists[0]['tracks'] = [track(1)]
        self.app.duplicate_playlist(0)
        self.app.store.playlists[1]['tracks'][0]['title'] = 'Changed'
        self.assertNotEqual(self.app.store.playlists[0]['tracks'][0]['title'], 'Changed')

    def test_name_collision_increments(self):
        self.app.create_playlist('Rock')
        self.app.back()
        self.app.duplicate_playlist(0)
        self.app.back()
        self.app.duplicate_playlist(0)
        names = [p['name'] for p in self.app.store.playlists]
        self.assertEqual(names, ['Rock', 'Rock (copy)', 'Rock (copy) 2'])

    def test_bad_index_noop(self):
        self.app.duplicate_playlist(5)
        self.assertEqual(self.app.store.playlists, [])

    def test_n_key(self):
        self.app.create_playlist('Rock')
        self.app.back()
        self.app.push('playlist', 0)
        s.handle_key(self.app, 'N')
        self.assertEqual(len(self.app.store.playlists), 2)

class SleepCustomTests(unittest.TestCase):
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

    def test_cycle_reaches_custom_modal(self):
        self.app.sleep_minutes = 90
        self.app.cycle_sleep()      # 90 -> eot
        self.assertTrue(self.app.sleep_eot)
        self.app.cycle_sleep()      # eot -> custom: prompt opens
        self.assertEqual(self.app.mode, 'sleep')
        self.assertEqual(self.app.sleep_buf, '')
        self.assertTrue(self.app.sleep_eot)   # timer state untouched yet

    def test_custom_value_arms_timer(self):
        self.app.mode = 'sleep'
        self.app.sleep_buf = '45'
        self.app.set_sleep_custom()
        self.assertEqual(self.app.mode, 'normal')
        self.assertEqual(self.app.sleep_minutes, 45)
        self.assertFalse(self.app.sleep_eot)
        self.assertIsNotNone(self.app.sleep_deadline)
        self.assertIn('45', self.app.toast[0])

    def test_invalid_input_keeps_timer(self):
        self.app.mode = 'sleep'
        self.app.sleep_buf = '9999'
        self.app.set_sleep_custom()
        self.assertIsNone(self.app.sleep_deadline)
        self.assertIn('unchanged', self.app.toast[0])

    def test_empty_input_keeps_timer(self):
        self.app.mode = 'sleep'
        self.app.sleep_buf = ''
        self.app.set_sleep_custom()
        self.assertIsNone(self.app.sleep_deadline)

    def test_cycle_with_custom_armed_does_not_crash(self):
        self.app.sleep_minutes = 45
        self.app.cycle_sleep()
        self.assertEqual(self.app.sleep_minutes, 15)

    def test_modal_keys(self):
        self.app.mode = 'sleep'
        for ch in '12':
            s.handle_key(self.app, ch)
        self.assertEqual(self.app.sleep_buf, '12')
        s.handle_key(self.app, 'x')          # ignored: digits only
        self.assertEqual(self.app.sleep_buf, '12')
        s.handle_key(self.app, '\x7f')
        self.assertEqual(self.app.sleep_buf, '1')
        s.handle_key(self.app, '\x1b')      # cancel
        self.assertEqual(self.app.mode, 'normal')
        self.assertEqual(self.app.sleep_buf, '')

    def test_modal_enter_arms(self):
        self.app.mode = 'sleep'
        s.handle_key(self.app, '2')
        s.handle_key(self.app, '0')
        s.handle_key(self.app, '\n')
        self.assertEqual(self.app.sleep_minutes, 20)
        self.assertEqual(self.app.mode, 'normal')

class PlayTileTests(unittest.TestCase):
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

    def test_liked_tile(self):
        self.app.store.liked = [track(1), track(2)]
        self.app.play = Mock()
        self.assertTrue(self.app.play_tile('liked', None))
        self.app.play.assert_called_once_with(self.app.store.liked, 0,
                                              source='Liked Songs')

    def test_playlist_tile(self):
        self.app.create_playlist('Rock')
        self.app.back()
        self.app.store.playlists[0]['tracks'] = [track(3)]
        self.app.play = Mock()
        self.assertTrue(self.app.play_tile('playlist', 0))
        self.app.play.assert_called_once_with([track(3)], 0, source='Rock')

    def test_empty_tile_toasts(self):
        self.app.play = Mock()
        self.assertFalse(self.app.play_tile('liked', None))
        self.app.play.assert_not_called()
        self.assertIn('Nothing', self.app.toast[0])

    def test_bad_index(self):
        self.assertFalse(self.app.play_tile('playlist', 9))

class FmtListenTests(unittest.TestCase):
    def test_under_an_hour(self):
        self.assertEqual(s.fmt_listen(45), '45 min')
        self.assertEqual(s.fmt_listen(0), '0 min')

    def test_hours(self):
        self.assertEqual(s.fmt_listen(130), '2 hr 10 min')
        self.assertEqual(s.fmt_listen(60), '1 hr 0 min')

class MergePlaylistTests(unittest.TestCase):
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
        self.app.create_playlist('A')
        self.app.back()
        self.app.create_playlist('B')
        self.app.back()
        self.app.store.playlists[0]['tracks'] = [track(1), track(2)]
        self.app.store.playlists[1]['tracks'] = [track(2), track(3)]

    def test_merge_skips_dupes(self):
        n = self.app.merge_playlist(0, 1)
        self.assertEqual(n, 1)
        self.assertEqual([t['id'] for t in self.app.store.playlists[1]['tracks']],
                         ['2', '3', '1'])
        self.assertIn('Merged 1 song', self.app.toast[0])

    def test_merge_all_dupes(self):
        self.app.store.playlists[1]['tracks'] = [track(1), track(2)]
        n = self.app.merge_playlist(0, 1)
        self.assertEqual(n, 0)
        self.assertIn('already', self.app.toast[0])

    def test_picker_excludes_source(self):
        self.app.open_pick_merge(0)
        names = [r['name'] for r in self.app.pick_rows]
        self.assertNotIn('A', names)
        self.assertIn('B', names)
        self.assertIn('Merge', self.app.pick_title)

    def test_picker_empty_playlist(self):
        self.app.store.playlists[0]['tracks'] = []
        self.app.open_pick_merge(0)
        self.assertNotEqual(self.app.mode, 'pick')
        self.assertIn('empty', self.app.toast[0])

    def test_picker_enter_merges(self):
        self.app.open_pick_merge(0)
        s.handle_key(self.app, 'j')     # select B
        s.handle_key(self.app, '\n')
        ids = [t['id'] for t in self.app.store.playlists[1]['tracks']]
        self.assertEqual(sorted(ids), ['1', '2', '3'])
        self.assertIsNone(self.app.pick_merge)
        self.assertEqual(self.app.mode, 'normal')

    def test_merge_into_new_playlist(self):
        self.app.open_pick_merge(0)
        s.handle_key(self.app, '\n')    # "+ New playlist" is row 0
        for ch in 'Mix':
            s.handle_key(self.app, ch)
        s.handle_key(self.app, '\n')
        names = [p['name'] for p in self.app.store.playlists]
        self.assertIn('Mix', names)
        mix = self.app.store.playlists[-1]
        self.assertEqual([t['id'] for t in mix['tracks']], ['1', '2'])
        self.assertIsNone(self.app.pick_merge)

    def test_b_key(self):
        self.app.push('playlist', 0)
        s.handle_key(self.app, 'B')
        self.assertEqual(self.app.mode, 'pick')
        self.assertEqual(self.app.pick_merge, 0)

class PinPlaylistTests(unittest.TestCase):
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
        self.app.create_playlist('A')
        self.app.back()
        self.app.create_playlist('B')
        self.app.back()
        self.app.create_playlist('C')
        self.app.back()

    def test_toggle_pin(self):
        self.app.toggle_pin(1)
        self.assertTrue(self.app.store.playlists[1]['pinned'])
        self.assertIn('Pinned B', self.app.toast[0])
        self.app.toggle_pin(1)
        self.assertFalse(self.app.store.playlists[1]['pinned'])
        self.assertIn('Unpinned B', self.app.toast[0])

    def test_toggle_pin_bad_index(self):
        self.app.toggle_pin(9)
        self.assertEqual([p.get('pinned') for p in self.app.store.playlists],
                         [None, None, None])

    def test_pinned_order_stable(self):
        self.app.toggle_pin(2)
        self.app.toggle_pin(0)
        self.assertEqual(self.app.pinned_order(), [0, 2, 1])
        self.app.toggle_pin(2)
        self.assertEqual(self.app.pinned_order(), [0, 1, 2])

    def test_pin_survives_reload(self):
        self.app.toggle_pin(1)
        store = s.Store()
        self.assertTrue(store.playlists[1].get('pinned'))

    def test_w_key(self):
        self.app.push('playlist', 2)
        s.handle_key(self.app, 'w')
        self.assertTrue(self.app.store.playlists[2]['pinned'])
        self.assertEqual(self.app.pinned_order(), [2, 0, 1])

class EnhancePlaylistTests(unittest.TestCase):
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
        self.app.create_playlist('Mix')
        self.app.back()
        self.app.store.playlists[0]['tracks'] = [
            dict(track(1), title='A One', artist='Alpha'), dict(track(2), title='A Two', artist='Alpha'),
            dict(track(3), title='B One', artist='Beta'), dict(track(4), title='B Two', artist='Beta')]
        # library pool: liked + history songs, some by the same artists
        self.app.store.liked = [dict(track(5), title='A Three', artist='Alpha'),
                                dict(track(6), title='C One', artist='Gamma')]
        self.app.store.history = [dict(track(7), title='A Four', artist='Alpha')]
        self.app.store.plays = {'5': {'n': 9, 'artist': 'Alpha',
                                      'title': 'A Three'},
                                '7': {'n': 4, 'artist': 'Alpha',
                                      'title': 'A Four'},
                                '6': {'n': 7, 'artist': 'Gamma',
                                      'title': 'C One'}}

    def test_enhance_interleaves(self):
        self.app.toggle_enhance(0)
        pl = self.app.store.playlists[0]
        self.assertTrue(pl['enhanced'])
        ids = [t['id'] for t in pl['tracks']]
        self.assertEqual(ids, ['1', '2', '5', '3', '4', '7'])
        enh = [t['id'] for t in pl['tracks'] if t.get('enhanced')]
        self.assertEqual(enh, ['5', '7'])   # 4 own songs -> 2 slots
        self.assertIn('2 suggestions', self.app.toast[0])

    def test_candidates_rank_same_artist_first(self):
        pl = self.app.store.playlists[0]
        cands = self.app.enhance_candidates(pl)
        self.assertEqual([t['id'] for t in cands], ['5', '7', '6'])

    def test_enhance_off_removes_suggestions(self):
        self.app.toggle_enhance(0)
        self.app.toggle_enhance(0)
        pl = self.app.store.playlists[0]
        self.assertFalse(pl['enhanced'])
        self.assertEqual([t['id'] for t in pl['tracks']],
                         ['1', '2', '3', '4'])
        self.assertIn('Enhance off', self.app.toast[0])

    def test_enhance_empty_playlist(self):
        self.app.store.playlists[0]['tracks'] = []
        self.app.toggle_enhance(0)
        self.assertIn('Add some songs', self.app.toast[0])
        self.assertFalse(self.app.store.playlists[0].get('enhanced'))

    def test_enhance_no_candidates(self):
        self.app.store.liked = []
        self.app.store.history = []
        self.app.toggle_enhance(0)
        self.assertIn('No suggestions', self.app.toast[0])
        self.assertFalse(self.app.store.playlists[0].get('enhanced'))

    def test_enhance_survives_reload(self):
        self.app.toggle_enhance(0)
        store = s.Store()
        self.assertTrue(store.playlists[0].get('enhanced'))
        self.assertTrue(any(t.get('enhanced')
                            for t in store.playlists[0]['tracks']))

    def test_duplicate_strips_suggestions(self):
        self.app.toggle_enhance(0)
        self.app.duplicate_playlist(0)
        copy = self.app.store.playlists[-1]
        self.assertEqual([t['id'] for t in copy['tracks']],
                         ['1', '2', '3', '4'])
        self.assertFalse(copy.get('enhanced'))

    def test_h_key(self):
        self.app.push('playlist', 0)
        s.handle_key(self.app, 'h')
        self.assertTrue(self.app.store.playlists[0]['enhanced'])

class PrivateSessionTests(unittest.TestCase):
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

    def test_default_off(self):
        self.assertFalse(self.app.private)

    def test_toggle_and_toast(self):
        self.app.toggle_private()
        self.assertTrue(self.app.private)
        self.assertIn("Private session on", self.app.toast[0])
        self.app.toggle_private()
        self.assertFalse(self.app.private)
        self.assertIn("Private session off", self.app.toast[0])

    def test_private_skips_recording(self):
        self.app.toggle_private()
        self.app._note_history(track(1))
        self.assertEqual(self.app.store.history, [])
        self.assertEqual(self.app.store.plays, {})

    def test_recording_resumes(self):
        self.app._note_history(track(1))
        self.app.toggle_private()
        self.app._note_history(track(2))
        self.app.toggle_private()
        self.app._note_history(track(3))
        ids = [h['id'] for h in self.app.store.history]
        self.assertEqual(ids, ['3', '1'])
        self.assertEqual(self.app.store.plays['1']['n'], 1)
        self.assertNotIn('2', self.app.store.plays)

    def test_session_only(self):
        self.app.toggle_private()
        with patch.object(s.threading.Thread, 'start'):
            fresh = s.App()
        self.assertFalse(fresh.private)

    def test_b_key(self):
        s.handle_key(self.app, 'b')
        self.assertTrue(self.app.private)
        s.handle_key(self.app, 'b')
        self.assertFalse(self.app.private)

class SongInfoTests(unittest.TestCase):
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
        self.app.create_playlist('Mix')
        self.app.back()

    def _seed(self):
        t = track(1)
        self.app.store.playlists[0]['tracks'] = [t]
        self.app.store.liked = [t]
        self.app.liked_ids.add(t['id'])
        self.app.store.history = [dict(t, added=1700000000.0)]
        self.app.store.plays = {'1': {'title': t['title'],
                                      'artist': t['artist'], 'n': 7}}
        return t

    def test_open_info(self):
        t = self._seed()
        self.app.open_info(t)
        self.assertEqual(self.app.mode, 'info')
        rows = dict(self.app.info_rows())
        self.assertEqual(rows['Title'], t['title'])
        self.assertEqual(rows['Liked'], 'yes')
        self.assertEqual(rows['In playlists'], 'Mix')
        self.assertIn('7 plays', rows['Plays'])
        self.assertIn('last', rows['Plays'])
        self.assertEqual(rows['Link'], t['url'])

    def test_open_info_empty(self):
        self.app.open_info(None)
        self.assertNotEqual(self.app.mode, 'info')
        self.assertIn('Nothing to show', self.app.toast[0])

    def test_info_rows_sparse(self):
        self.app.open_info(track(9))
        rows = dict(self.app.info_rows())
        self.assertEqual(rows['Plays'], '0 plays')
        self.assertEqual(rows['Liked'], 'no')
        self.assertEqual(rows['In playlists'], '-')

    def test_i_key_and_close(self):
        t = self._seed()
        self.app.push('playlist', 0)
        s.handle_key(self.app, 'I')
        self.assertEqual(self.app.mode, 'info')
        s.handle_key(self.app, '\x1b')
        self.assertEqual(self.app.mode, 'normal')
        self.assertIsNone(self.app.info_track)

    def test_y_copies_from_modal(self):
        t = self._seed()
        self.app.open_info(t)
        seen = []
        self.app.copy_link = lambda x: seen.append(x)
        s.handle_key(self.app, 'Y')
        self.assertEqual(seen, [self.app.info_track])
        self.assertEqual(self.app.mode, 'info')   # stays open

class OpenBrowserTests(unittest.TestCase):
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
        self.popen = patch.object(s.subprocess, 'Popen')
        self.mock_popen = self.popen.start()
        self.addCleanup(self.popen.stop)

    def test_opens_with_available_opener(self):
        with patch.object(s.shutil, 'which',
                          side_effect=lambda n: '/bin/xdg-open'
                          if n == 'xdg-open' else None):
            ok = self.app.open_in_browser(track(1))
        self.assertTrue(ok)
        self.mock_popen.assert_called_once()
        args = self.mock_popen.call_args[0][0]
        self.assertEqual(args, ['/bin/xdg-open', track(1)['url']])
        self.assertIn('Opening Song 1 in browser', self.app.toast[0])

    def test_prefers_termux(self):
        with patch.object(s.shutil, 'which',
                          side_effect=lambda n: f'/bin/{n}'):
            self.app.open_in_browser(track(1))
        args = self.mock_popen.call_args[0][0]
        self.assertEqual(args[0], '/bin/termux-open-url')

    def test_no_opener_shows_link(self):
        with patch.object(s.shutil, 'which', return_value=None):
            ok = self.app.open_in_browser(track(1))
        self.assertFalse(ok)
        self.mock_popen.assert_not_called()
        self.assertIn('No browser opener', self.app.toast[0])
        self.assertIn(track(1)['url'], self.app.toast[0])

    def test_no_url(self):
        ok = self.app.open_in_browser({'id': 'x', 'title': 'T'})
        self.assertFalse(ok)
        self.assertIn('No link', self.app.toast[0])

    def test_popen_failure(self):
        self.mock_popen.side_effect = OSError('nope')
        with patch.object(s.shutil, 'which', return_value='/bin/xdg-open'):
            ok = self.app.open_in_browser(track(1))
        self.assertFalse(ok)
        self.assertIn('Could not open', self.app.toast[0])

    def test_o_key(self):
        self.app.create_playlist('Mix')
        self.app.back()
        self.app.store.playlists[0]['tracks'] = [track(1)]
        self.app.push('playlist', 0)
        with patch.object(s.shutil, 'which', return_value='/bin/xdg-open'):
            s.handle_key(self.app, 'O')
        self.assertTrue(self.mock_popen.called)

class UndoDeleteTests(unittest.TestCase):
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
        self.app.create_playlist('A')
        self.app.back()
        self.app.create_playlist('B')
        self.app.back()
        self.app.store.playlists[0]['tracks'] = [track(1), track(2)]
        self.app.store.playlists[1]['tracks'] = [track(3)]

    def test_undo_playlist(self):
        self.app.delete_playlist(0)
        self.assertEqual([p['name'] for p in self.app.store.playlists], ['B'])
        self.app.undo_delete()
        self.assertEqual([p['name'] for p in self.app.store.playlists],
                         ['A', 'B'])
        self.assertEqual(self.app.store.playlists[0]['tracks'],
                         [track(1), track(2)])
        self.assertIn('Restored playlist: A', self.app.toast[0])

    def test_undo_track(self):
        self.app.push('playlist', 0)
        self.app.sel[self.app.key()] = 1     # select Song 2
        self.app.delete_selected()
        self.assertEqual(self.app.store.playlists[0]['tracks'], [track(1)])
        self.app.undo_delete()
        self.assertEqual(self.app.store.playlists[0]['tracks'],
                         [track(1), track(2)])
        self.assertIn('Restored Song 2', self.app.toast[0])

    def test_undo_empty(self):
        self.app.undo_delete()
        self.assertIn('Nothing to restore', self.app.toast[0])

    def test_undo_is_one_level(self):
        self.app.delete_playlist(0)
        self.app.undo_delete()
        self.app.undo_delete()
        self.assertIn('Nothing to restore', self.app.toast[0])

    def test_undo_track_gone_playlist(self):
        self.app.push('playlist', 0)
        self.app.sel[self.app.key()] = 0
        self.app.delete_selected()
        self.app._trash = ('track', 9, 0, track(1))
        self.app.undo_delete()
        self.assertIn('That playlist is gone', self.app.toast[0])

    def test_latest_delete_wins(self):
        self.app.delete_playlist(0)
        self.app.delete_playlist(0)     # now deletes B
        self.app.undo_delete()
        names = [p['name'] for p in self.app.store.playlists]
        self.assertEqual(names, ['B'])  # only B restored

    def test_u_key(self):
        self.app.delete_playlist(0)
        s.handle_key(self.app, 'U')
        self.assertEqual([p['name'] for p in self.app.store.playlists],
                         ['A', 'B'])

class LikeAllTests(unittest.TestCase):
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
        self.app.create_playlist('Mix')
        self.app.back()
        self.app.store.playlists[0]['tracks'] = [track(1), track(2), track(3)]

    def test_like_all(self):
        self.app.like_all(0)
        self.assertEqual([t['id'] for t in self.app.store.liked],
                         ['1', '2', '3'])
        self.assertIn('Liked 3 songs from Mix', self.app.toast[0])
        for i in '123':
            self.assertIn(i, self.app.liked_ids)

    def test_like_all_skips_liked(self):
        self.app.like(track(2))
        self.app.like_all(0)
        self.assertEqual([t['id'] for t in self.app.store.liked],
                         ['1', '3', '2'])
        self.assertIn('Liked 2 songs', self.app.toast[0])

    def test_like_all_already_all_liked(self):
        self.app.like_all(0)
        self.app.like_all(0)
        self.assertIn('already liked', self.app.toast[0])
        self.assertEqual(len(self.app.store.liked), 3)

    def test_like_all_empty(self):
        self.app.store.playlists[0]['tracks'] = []
        self.app.like_all(0)
        self.assertIn('empty', self.app.toast[0])
        self.assertEqual(self.app.store.liked, [])

    def test_like_all_bad_index(self):
        self.app.like_all(9)
        self.assertEqual(self.app.store.liked, [])

    def test_L_key(self):
        self.app.push('playlist', 0)
        s.handle_key(self.app, 'L')
        self.assertEqual(len(self.app.store.liked), 3)

    def test_like_all_persists(self):
        self.app.like_all(0)
        self.assertEqual(len(s.Store().liked), 3)

class HideSongTests(unittest.TestCase):
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

    def test_toggle_block_and_toast(self):
        self.app.toggle_block(track(1))
        self.assertIn('1', self.app.blocked_ids)
        self.assertIn("Won't suggest Song 1 again", self.app.toast[0])
        self.app.toggle_block(track(1))
        self.assertNotIn('1', self.app.blocked_ids)
        self.assertIn('back in suggestions', self.app.toast[0])

    def test_block_persists(self):
        self.app.toggle_block(track(1))
        self.assertEqual(s.Store().blocked, ['1'])

    def test_block_none(self):
        self.app.toggle_block(None)
        self.assertEqual(self.app.blocked_ids, set())

    def test_enhance_skips_blocked(self):
        self.app.create_playlist('Mix')
        self.app.back()
        self.app.store.playlists[0]['tracks'] = [track(1)]
        self.app.store.liked = [track(2), track(3)]
        self.app.toggle_block(track(3))
        cands = self.app.enhance_candidates(self.app.store.playlists[0])
        self.assertEqual([t['id'] for t in cands], ['2'])

    def test_daily_mixes_skip_blocked(self):
        self.app.store.liked = [dict(track(1), artist='A One'),
                                dict(track(2), artist='A One'),
                                dict(track(3), artist='A One')]
        self.app.store.plays = {'1': {'n': 5, 'artist': 'A One',
                                      'title': 'Song 1'}}
        with_blocked = dict(track(3), artist='A One')
        self.app.store.blocked = ['3']
        mixes = s.daily_mixes(self.app.store)
        all_ids = {t['id'] for m in mixes for t in m['tracks']}
        self.assertNotIn('3', all_ids)
        self.assertIn('1', all_ids)

    def test_similar_view_skips_blocked(self):
        self.app.store.similar = {'items': [track(1), track(2)], 'pool': []}
        self.app.toggle_block(track(2))
        self.app.push('similar', None)
        self.assertEqual([t['id'] for t in self.app.view_tracks()], ['1'])

    def test_info_rows_show_hidden(self):
        self.app.toggle_block(track(1))
        self.app.open_info(track(1))
        rows = dict(self.app.info_rows())
        self.assertEqual(rows['Suggested'], 'no (hidden)')

    def test_x_key(self):
        self.app.create_playlist('Mix')
        self.app.back()
        self.app.store.playlists[0]['tracks'] = [track(1)]
        self.app.push('playlist', 0)
        s.handle_key(self.app, 'x')
        self.assertIn('1', self.app.blocked_ids)

class CopyTracklistTests(unittest.TestCase):
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
        self.app.create_playlist('Mix')
        self.app.back()
        self.app.store.playlists[0]['tracks'] = [
            dict(track(1), title='One', artist='A', dur=61),
            dict(track(2), title='Two', artist='B', dur=None)]

    def test_tracklist_text(self):
        self.app.copy_text = Mock(return_value=True)
        text = self.app.copy_tracklist(0)
        self.assertEqual(text, 'Mix\n1. One - A (1:01)\n2. Two - B')
        self.assertEqual(self.app.copy_text.call_args[0][0], text)

    def test_tracklist_toast_on_copy(self):
        with patch.object(s.shutil, 'which', return_value=None),              patch('builtins.open', side_effect=OSError('no tty')):
            self.app.copy_tracklist(0)
        self.assertIn('Tracklist:', self.app.toast[0])

    def test_tracklist_empty(self):
        self.app.store.playlists[0]['tracks'] = []
        self.assertIsNone(self.app.copy_tracklist(0))
        self.assertIn('empty', self.app.toast[0])

    def test_tracklist_bad_index(self):
        self.assertIsNone(self.app.copy_tracklist(9))

    def test_V_key(self):
        self.app.copy_text = Mock(return_value=True)
        self.app.push('playlist', 0)
        s.handle_key(self.app, 'V')
        self.assertTrue(self.app.copy_text.called)

class ShareStatsTests(unittest.TestCase):
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
        self.app.store.liked = [dict(track(1), dur=180)]
        self.app.store.history = [dict(track(1), added=__import__('time').time())]
        self.app.store.plays = {
            '1': {'title': 'Song 1', 'artist': 'Artist', 'n': 7},
            '2': {'title': 'Song 2', 'artist': 'Artist', 'n': 3},
            '3': {'title': 'Song 3', 'artist': 'Other', 'n': 2}}

    def test_share_text(self):
        text = self.app.stats_share_text()
        lines = text.split('\n')
        self.assertEqual(lines[0], 'My SpotUI stats')
        self.assertIn('12 plays · 3 different songs', lines[1])
        self.assertIn('21 min', text)
        self.assertIn('Top artist: Artist (10 plays)', text)
        self.assertIn('Top song: Song 1 - Artist (7 plays)', text)
        self.assertIn('1-day streak', text)
        self.assertIn('1 plays this week', text)

    def test_share_stats_copies(self):
        self.app.copy_text = Mock(return_value=True)
        text = self.app.share_stats()
        self.assertEqual(self.app.copy_text.call_args[0][0], text)

    def test_share_stats_fallback(self):
        self.app.copy_text = Mock(return_value=False)
        self.app.share_stats()
        self.assertIn('Stats:', self.app.toast[0])

    def test_Y_in_stats_view(self):
        self.app.copy_text = Mock(return_value=True)
        self.app.push('stats', None)
        s.handle_key(self.app, 'Y')
        self.assertTrue(self.app.copy_text.called)

    def test_empty_stats(self):
        self.app.store.plays = {}
        self.app.store.history = []
        self.app.store.liked = []
        text = self.app.stats_share_text()
        self.assertEqual(text, 'My SpotUI stats\n0 plays · 0 different songs')



class LibraryShuffleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for name, value in [('CFG', root), ('STORE', root / 'library.json')]:
            p = patch.object(s, name, value)
            p.start()
            self.addCleanup(p.stop)
        tp = patch.object(s.threading.Thread, 'start')
        tp.start()
        self.addCleanup(tp.stop)
        self.app = s.App()
        self.app._play_current = Mock()

    def seed(self):
        self.app.store.liked = [dict(track(1)), dict(track(2))]
        self.app.store.history = [dict(track(2)), dict(track(3))]
        self.app.store.playlists = [
            {"name": "Mix", "tracks": [dict(track(3)), dict(track(4))]}]
        self.app.store.save = Mock()

    def test_library_tracks_dedupes(self):
        self.seed()
        ids = [t["id"] for t in self.app.library_tracks()]
        self.assertEqual(sorted(ids), ["1", "2", "3", "4"])
        self.assertEqual(len(ids), len(set(ids)))

    def test_shuffle_library_skips_blocked(self):
        self.seed()
        self.app.blocked_ids = {"2"}
        self.app.shuffle_library()
        self.assertEqual(len(self.app.queue), 3)
        self.assertNotIn("2", [t["id"] for t in self.app.queue])
        self.assertEqual(self.app.play_source, "Library shuffle")

    def test_shuffle_library_plays_all(self):
        self.seed()
        self.app.shuffle_library()
        self.assertEqual(len(self.app.queue), 4)
        self.assertTrue(all(t.get("src") == "Library shuffle"
                            for t in self.app.queue))
        self.app._play_current.assert_called_once()

    def test_shuffle_library_empty_toasts(self):
        self.app.toast_now = Mock()
        self.app.shuffle_library()
        self.assertEqual(self.app.queue, [])
        self.app.toast_now.assert_called_once()

    def test_z_key_shuffles_library(self):
        self.seed()
        self.app.mode = "normal"
        self.app.shuffle_library = Mock()
        s.handle_key(self.app, 'Z')
        self.app.shuffle_library.assert_called_once()


class DedupePlaylistTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for name, value in [('CFG', root), ('STORE', root / 'library.json')]:
            p = patch.object(s, name, value)
            p.start()
            self.addCleanup(p.stop)
        tp = patch.object(s.threading.Thread, 'start')
        tp.start()
        self.addCleanup(tp.stop)
        self.app = s.App()
        self.app.store.playlists = [{"name": "Mix", "tracks": [
            dict(track(1)), dict(track(2)), dict(track(1)),
            dict(track(3)), dict(track(2))]}]
        self.app.store.save = Mock()

    def ids(self):
        return [t["id"] for t in self.app.store.playlists[0]["tracks"]]

    def test_dedupe_keeps_first_copy(self):
        self.app.dedupe_playlist(0)
        self.assertEqual(self.ids(), ["1", "2", "3"])

    def test_dedupe_sets_undo_trash(self):
        self.app.dedupe_playlist(0)
        kind, pi, items = self.app._trash
        self.assertEqual(kind, "tracks")
        self.assertEqual(pi, 0)
        self.assertEqual([t["id"] for _, t in items], ["1", "2"])

    def test_undo_restores_original_positions(self):
        self.app.dedupe_playlist(0)
        self.app.undo_delete()
        self.assertEqual(self.ids(), ["1", "2", "1", "3", "2"])

    def test_no_duplicates_toasts_and_keeps_list(self):
        self.app.store.playlists[0]["tracks"] = [dict(track(1)),
                                                 dict(track(2))]
        self.app.toast_now = Mock()
        self.app.dedupe_playlist(0)
        self.assertEqual(self.ids(), ["1", "2"])
        self.assertIsNone(self.app._trash)
        self.assertIn("No duplicates",
                      self.app.toast_now.call_args[0][0])

    def test_bad_index_is_safe(self):
        self.app.dedupe_playlist(9)

    def test_h_key_dedupes_playlist(self):
        self.app.mode = "normal"
        self.app.stack = [("playlist", 0)]
        s.handle_key(self.app, 'H')
        self.assertEqual(self.ids(), ["1", "2", "3"])


class SeekPercentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for name, value in [('CFG', root), ('STORE', root / 'library.json')]:
            p = patch.object(s, name, value)
            p.start()
            self.addCleanup(p.stop)
        tp = patch.object(s.threading.Thread, 'start')
        tp.start()
        self.addCleanup(tp.stop)
        self.app = s.App()
        self.app._play_current = Mock()
        self.app.play([dict(track(1), dur=200)], 0)
        self.app.current = self.app.queue[0]
        self.app.mpv.seek_abs = Mock()
        self.app.mpv.state["dur"] = 200.0

    def test_seek_halfway(self):
        self.app.seek_percent(50)
        self.app.mpv.seek_abs.assert_called_once_with(100.0)

    def test_seek_zero_goes_to_start(self):
        self.app.seek_percent(0)
        self.app.mpv.seek_abs.assert_called_once_with(0.0)

    def test_no_duration_toasts_instead(self):
        self.app.mpv.state["dur"] = 0.0
        self.app.toast_now = Mock()
        self.app.seek_percent(50)
        self.app.mpv.seek_abs.assert_not_called()
        self.app.toast_now.assert_called_once()

    def test_digit_key_seeks_in_playing_view(self):
        self.app.mode = "normal"
        self.app.stack = [("playing", None)]
        s.handle_key(self.app, '5')
        self.app.mpv.seek_abs.assert_called_once_with(100.0)

    def test_digit_key_ignored_elsewhere(self):
        self.app.mode = "normal"
        self.app.stack = [("liked", None)]
        s.handle_key(self.app, '5')
        self.app.mpv.seek_abs.assert_not_called()


class TuiImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for name, value in [('CFG', root), ('STORE', root / 'library.json')]:
            p = patch.object(s, name, value)
            p.start()
            self.addCleanup(p.stop)
        tp = patch.object(s.threading.Thread, 'start')
        tp.start()
        self.addCleanup(tp.stop)
        self.app = s.App()
        self.export = root / "mix.json"
        self.export.write_text(json.dumps(
            {"name": "Roadtrip",
             "tracks": [dict(track(1)), dict(track(2))]}),
            encoding="utf-8")

    def test_import_adds_playlist_and_opens_it(self):
        self.app.import_playlist_file(str(self.export))
        self.assertEqual(self.app.store.playlists[-1]["name"], "Roadtrip")
        self.assertEqual(len(self.app.store.playlists[-1]["tracks"]), 2)
        self.assertEqual(self.app.stack[-1],
                         ("playlist", len(self.app.store.playlists) - 1))

    def test_import_rejects_non_playlist_json(self):
        bad = Path(self.tmp.name) / "bad.json"
        bad.write_text('{"foo": 1}', encoding="utf-8")
        self.app.toast_now = Mock()
        n = len(self.app.store.playlists)
        self.app.import_playlist_file(str(bad))
        self.assertEqual(len(self.app.store.playlists), n)
        self.assertIn("Not a SpotUI playlist file",
                      self.app.toast_now.call_args[0][0])

    def test_import_missing_file_toasts(self):
        self.app.toast_now = Mock()
        self.app.import_playlist_file(str(Path(self.tmp.name) / "gone.json"))
        self.assertIn("Could not read", self.app.toast_now.call_args[0][0])

    def test_json_path_in_create_modal_imports(self):
        self.app.mode = "name"
        self.app.name_buf = str(self.export)
        s.handle_key(self.app, '\n')
        self.assertEqual(self.app.mode, "normal")
        self.assertEqual(self.app.store.playlists[-1]["name"], "Roadtrip")

    def test_plain_name_still_creates_empty_playlist(self):
        self.app.mode = "name"
        self.app.name_buf = "Fresh list"
        s.handle_key(self.app, '\n')
        self.assertEqual(self.app.store.playlists[-1]["name"], "Fresh list")
        self.assertEqual(self.app.store.playlists[-1]["tracks"], [])


class SortPlaysTests(unittest.TestCase):
    def test_sort_by_play_count_desc(self):
        plays = {"1": {"n": 5}, "2": {"n": 40}, "3": {"n": 12}}
        out = s.sort_tracks([track(1), track(2), track(3)], "plays", plays)
        self.assertEqual([t["id"] for t in out], ["2", "3", "1"])

    def test_unplayed_songs_sort_last(self):
        plays = {"2": {"n": 3}}
        out = s.sort_tracks([track(1), track(2), track(3)], "plays", plays)
        self.assertEqual(out[0]["id"], "2")
        self.assertEqual([t["id"] for t in out[1:]], ["1", "3"])

    def test_plays_none_is_safe(self):
        out = s.sort_tracks([track(1), track(2)], "plays")
        self.assertEqual(len(out), 2)

    def test_plays_mode_in_cycle_and_label(self):
        self.assertIn("plays", s.SORT_MODES)
        self.assertEqual(s.SORT_LABEL["plays"], "Most played first")

    def test_view_uses_store_plays(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        for name, value in [('CFG', root), ('STORE', root / 'library.json')]:
            p = patch.object(s, name, value)
            p.start()
            self.addCleanup(p.stop)
        tp = patch.object(s.threading.Thread, 'start')
        tp.start()
        self.addCleanup(tp.stop)
        app = s.App()
        app.store.liked = [dict(track(1)), dict(track(2))]
        app.store.plays = {"2": {"n": 9}}
        app.store.sort_mode = "plays"
        app.stack = [("liked", None)]
        self.assertEqual([t["id"] for t in app.view_tracks()], ["2", "1"])


class ContextMenuTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for name, value in [('CFG', root), ('STORE', root / 'library.json')]:
            p = patch.object(s, name, value)
            p.start()
            self.addCleanup(p.stop)
        tp = patch.object(s.threading.Thread, 'start')
        tp.start()
        self.addCleanup(tp.stop)
        self.app = s.App()
        self.app._play_current = Mock()
        self.app.store.liked = [dict(track(1)), dict(track(2))]
        self.app.liked_ids = {"1", "2"}
        self.app.stack = [("liked", None)]

    def open_menu(self, idx=0):
        t = self.app.store.liked[idx]
        self.app.open_context(t, "liked:", idx, 10, 5)

    def test_items_reflect_like_state(self):
        self.open_menu()
        labels = [l for l, _ in self.app.context_items()]
        self.assertIn("Unlike", labels)
        self.assertIn("Hide from suggestions", labels)
        self.assertEqual(self.app.mode, "context")

    def test_items_reflect_block_state(self):
        self.app.blocked_ids = {"1"}
        self.open_menu()
        labels = [l for l, _ in self.app.context_items()]
        self.assertIn("Unhide from suggestions", labels)

    def test_exec_runs_action_and_closes(self):
        self.open_menu()
        self.app.play_next = Mock()
        self.app.context_exec(1)
        self.app.play_next.assert_called_once()
        self.assertEqual(self.app.mode, "normal")

    def test_esc_closes(self):
        self.open_menu()
        s.handle_key(self.app, '\x1b')
        self.assertEqual(self.app.mode, "normal")
        self.assertIsNone(self.app.ctx)

    def test_j_k_move_selection_with_clamp(self):
        self.open_menu()
        s.handle_key(self.app, 'k')
        self.assertEqual(self.app.ctx["sel"], 0)
        s.handle_key(self.app, 'j')
        s.handle_key(self.app, 'j')
        self.assertEqual(self.app.ctx["sel"], 2)
        for _ in range(10):
            s.handle_key(self.app, 'j')
        self.assertEqual(self.app.ctx["sel"],
                         len(self.app.context_items()) - 1)

    def test_enter_executes_selected(self):
        self.open_menu()
        self.app.like = Mock()
        s.handle_key(self.app, 'j')   # Play next
        s.handle_key(self.app, 'j')   # Add to queue
        s.handle_key(self.app, 'j')   # Unlike
        s.handle_key(self.app, '\n')
        self.app.like.assert_called_once()

    def test_right_click_on_row_opens_menu(self):
        self.app.rects = [{"x0": 0, "y0": 0, "x1": 20, "y1": 1,
                           "act": "row", "arg": ("liked:", 1, False)}]
        b3 = getattr(s.curses, "BUTTON3_PRESSED", 2097152)
        with patch.object(s.curses, "getmouse",
                          return_value=(0, 5, 0, 0, b3)):
            s.handle_mouse(self.app)
        self.assertEqual(self.app.mode, "context")
        self.assertEqual(self.app.ctx["track"]["id"], "2")

    def test_right_click_outside_rows_does_nothing(self):
        self.app.rects = [{"x0": 0, "y0": 0, "x1": 20, "y1": 1,
                           "act": "nav", "arg": "home"}]
        b3 = getattr(s.curses, "BUTTON3_PRESSED", 2097152)
        with patch.object(s.curses, "getmouse",
                          return_value=(0, 5, 0, 0, b3)):
            s.handle_mouse(self.app)
        self.assertEqual(self.app.mode, "normal")
        self.assertIsNone(self.app.ctx)

    def test_ctxrow_click_executes(self):
        self.open_menu()
        self.app.copy_link = Mock()
        self.app.rects = [{"x0": 1, "y0": 3, "x1": 27, "y1": 4,
                           "act": "ctxrow", "arg": 5}]
        with patch.object(s.curses, "getmouse",
                          return_value=(0, 5, 3, 0, s.curses.BUTTON1_CLICKED)):
            s.handle_mouse(self.app)
        self.app.copy_link.assert_called_once()


class QueueContextTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for name, value in [('CFG', root), ('STORE', root / 'library.json')]:
            p = patch.object(s, name, value)
            p.start()
            self.addCleanup(p.stop)
        tp = patch.object(s.threading.Thread, 'start')
        tp.start()
        self.addCleanup(tp.stop)
        self.app = s.App()
        self.app._play_current = Mock()
        self.app.play([dict(track(i)) for i in range(1, 6)], 1)
        self.app.toast_now = Mock()

    def open_queue_menu(self, idx):
        self.app.open_context(self.app.queue[idx], "queue:", idx, 10, 5)

    def labels(self):
        return [l for l, _ in self.app.context_items()]

    def test_upcoming_row_actions(self):
        self.open_queue_menu(3)
        self.assertEqual(self.labels()[:3],
                         ["Play now", "Move up next", "Remove from queue"])

    def test_playing_row_hides_move_actions(self):
        self.open_queue_menu(1)
        self.assertNotIn("Play now", self.labels())
        self.assertNotIn("Move up next", self.labels())
        self.assertNotIn("Remove from queue", self.labels())
        self.assertIn("Song info", self.labels())

    def test_remove_queue_at(self):
        self.app.remove_queue_at(3)
        self.assertEqual([t["id"] for t in self.app.queue],
                         ["1", "2", "3", "5"])
        self.assertEqual(self.app.qpos, 1)

    def test_remove_before_playing_shifts_qpos(self):
        self.app.remove_queue_at(0)
        self.assertEqual(self.app.qpos, 0)
        self.assertEqual(len(self.app.queue), 4)

    def test_queue_to_next_from_upcoming(self):
        self.app.queue_to_next(4)
        self.assertEqual([t["id"] for t in self.app.queue],
                         ["1", "2", "5", "3", "4"])
        self.assertEqual(self.app.qpos, 1)

    def test_queue_to_next_from_past(self):
        self.app.queue_to_next(0)
        self.assertEqual([t["id"] for t in self.app.queue],
                         ["2", "1", "3", "4", "5"])
        self.assertEqual(self.app.qpos, 0)

    def test_queue_to_next_noop_on_playing(self):
        q = list(self.app.queue)
        self.app.queue_to_next(1)
        self.assertEqual(self.app.queue, q)

    def test_exec_remove_via_menu(self):
        self.open_queue_menu(3)
        self.app.context_exec(2)
        self.assertEqual(len(self.app.queue), 4)
        self.assertEqual(self.app.mode, "normal")
