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

    def test_theme_cycle_persists(self):
        self.app.pal = Mock()
        self.app.pal.apply_theme.return_value = True
        s.handle_key(self.app, 'T')
        self.assertEqual(self.app.store.theme, s.THEME_NAMES[1])
        self.assertEqual(s.Store().theme, s.THEME_NAMES[1])

    def test_theme_refused_without_palette(self):
        self.app.pal = Mock()
        self.app.pal.apply_theme.return_value = False
        s.handle_key(self.app, 'T')
        self.assertEqual(self.app.store.theme, s.THEME_NAMES[0])

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
                                   "n": 1, "has": True})
        self.assertEqual(rows[2], {"name": "Empty", "new": False,
                                   "n": 0, "has": False})
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
        now = _t.time()
        store.history = [
            {"id": "1", "added": now - 3600, "dur": 180},        # today 3m
            {"id": "2", "added": now - 3600, "dur": 120},        # today +2m
            {"id": "3", "added": now - 26 * 3600, "dur": 600},   # yesterday 10m
            {"id": "4", "added": now - 8 * 86400, "dur": 300},   # outside
            {"id": "5", "added": now - 3600},                    # no dur
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
        for _ in range(6):
            self.app.cycle_sleep()
            seen.append("eot" if self.app.sleep_eot
                        else self.app.sleep_minutes)
        self.assertEqual(seen, [15, 30, 60, 90, "eot", 0])
        self.assertIsNone(self.app.sleep_deadline)

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
