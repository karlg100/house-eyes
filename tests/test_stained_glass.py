"""Stained-glass integration and pane-lighting checks; no GPU/GPIO needed."""
from pathlib import Path
import sys
import threading
import types
import unittest
from unittest.mock import Mock

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eyes"))
sys.path.insert(0, str(ROOT / "tools"))
from preview_christmas import draw_scene, load_scene, tree_gain, glass_window_colour
from seasonal import NoseGlow, theme_options
from stained_glass import lighting_parameters


class GlassTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scene = load_scene("stained-glass")

    def test_only_two_glass_eyes_and_stationary_tree(self):
        scene = self.scene
        scene["gazeInput"] = types.SimpleNamespace(
            get=lambda now: ([(0.7,0.1),(1,-1),(-0.7,0.2)],True,0.9))
        scene["lastFrameTime"] -= 1
        drawn = draw_scene(scene)
        self.assertIsNone(scene["decor"])
        self.assertIsNone(scene["noseGlow"])
        for name in ("centerEye", "centerIris", "centerUpperEyelid", "centerLowerEyelid"):
            self.assertNotIn(scene[name],drawn)
        for name in ("leftEye","rightEye","leftIris","rightIris"):
            self.assertNotIn(scene[name],drawn)
        panels=scene["glassDecor"].panels
        self.assertEqual(len(panels),3)
        self.assertTrue(all(panel in drawn for panel in panels))
        self.assertGreater(panels[0].custom_data[48],0)
        self.assertLess(panels[2].custom_data[48],0)
        self.assertEqual([panel.custom_data[54] for panel in panels],[1,0,1])
        tree = scene["glassDecor"].tree
        self.assertIn(tree,drawn)
        self.assertEqual((tree.rx,tree.ry),(0,0))
        self.assertEqual(len(tree.textures),2)
        self.assertTrue(np.isfinite(tree.custom_data).all())

    def test_full_window_stays_glass_during_blink(self):
        panel=self.scene["glassDecor"].panels[0]
        # Check a grid over the full rectangle, including well outside the
        # eye silhouette. A closed eye must reveal the same glass background.
        u,v=np.meshgrid(np.linspace(0.03,0.97,30),np.linspace(0.03,0.97,40))
        uv=np.stack([u,v],axis=-1)
        params=panel.custom_data[48:57].copy()
        params[3]=1
        closed=glass_window_colour(uv,*panel.textures,params)
        params[6]=0
        background=glass_window_colour(uv,*panel.textures,params)
        outside=(np.abs((uv[...,1]-.5)*params[5]) > .05)
        np.testing.assert_allclose(closed[outside],background[outside])
        self.assertGreater(np.mean(background.max(axis=-1)>30),.9)

    def test_gaze_and_blink_carry_the_surrounding_glass(self):
        panel=self.scene["glassDecor"].panels[0]
        u,v=np.meshgrid(np.linspace(.08,.92,40),np.linspace(.05,.95,50))
        uv=np.stack([u,v],axis=-1)
        params=panel.custom_data[48:57].copy()
        params[:4]=(0,0,.5,0)
        params[6]=0  # inspect just the glass, without eye colouring
        base=glass_window_colour(uv,*panel.textures,params)
        params[:2]=(.3,-.1)
        moved=glass_window_colour(uv,*panel.textures,params)
        far_from_eye=np.abs((v-.5)*params[5]) > .8
        self.assertGreater(np.mean(np.abs(moved[far_from_eye]-base[far_from_eye])),8)
        params[:2]=(0,0)
        params[3]=1
        blink=glass_window_colour(uv,*panel.textures,params)
        self.assertGreater(np.mean(np.abs(blink[far_from_eye]-base[far_from_eye])),8)
        # The frame stays registered to the real window as its interior moves.
        edge_uv=np.array([[0,.25],[1,.75],[.25,0],[.75,1]])
        still=glass_window_colour(edge_uv,*panel.textures,params)
        params[:2]=(.3,-.1)
        params[3]=0
        np.testing.assert_allclose(glass_window_colour(edge_uv,*panel.textures,params),still)

    def test_tree_messages_preserve_gaze_and_reject_nose_commands(self):
        scene = self.scene
        receiver = scene["GazeInput"].__new__(scene["GazeInput"])
        receiver.lock = threading.Lock()
        receiver.target, receiver.stamp = None,0
        receiver.sock = Mock()
        receiver.sock.recv.side_effect = [b"-1 0 0 0 1 0 p=1",SystemExit]
        with self.assertRaises(SystemExit): receiver.run()
        target,stamp = receiver.target,receiver.stamp
        receiver.sock.recv.side_effect = [b"tree off",b"nose on",b"tree pulse nan",SystemExit]
        with self.assertRaises(SystemExit): receiver.run()
        self.assertEqual(scene["treeGlow"].mode,"off")
        self.assertEqual(receiver.target,target)
        self.assertEqual(receiver.stamp,stamp)
        self.assertIsNone(receiver.get(stamp+3))

    def test_timed_sweep_returns_to_previous_mode(self):
        now = [10.0]
        control = NoseGlow("off",clock=lambda:now[0],command_word="tree")
        self.assertFalse(control.command("nose on"))
        self.assertTrue(control.command("tree pulse 6"))
        now[0] = 12
        params = lighting_parameters(control,10)
        self.assertAlmostEqual(params[2],1/3)
        self.assertEqual(params[3],1)
        now[0] = 16.1
        params = lighting_parameters(control,10)
        self.assertEqual(params[1],0)
        self.assertEqual(params[3],0)
        self.assertTrue(control.command("tree auto"))
        self.assertEqual(lighting_parameters(control,10)[3],1)

    def test_light_preserves_colours_and_star_finishes_sweep(self):
        panes = np.array([[0.25,0.08,1],[0.5,0.5,1],[0.75,0.85,1],[0,0,0]])
        on = tree_gain(panes,(0,0,0,0,1,0))
        off = tree_gain(panes,(0,0,0,0,0,0))
        np.testing.assert_allclose(on[:3],1)
        np.testing.assert_allclose(off[:3],0.36)
        early = tree_gain(panes,(2,1,0.2,1,0,0))
        late = tree_gain(panes,(2,1,0.8,1,0,0))
        self.assertGreater(early[2],late[2])
        self.assertGreater(late[0],early[0])
        for t in np.linspace(0,1,20):
            gain = tree_gain(panes,(t*20,1,t,1,0,0))
            self.assertTrue(((0 <= gain) & (gain <= 1)).all())
            self.assertEqual(gain[3],0.73)

    def test_glass_geometry_and_alpha_assets(self):
        scene = self.scene
        for name in ("pupilMinPts","pupilMaxPts"):
            points = np.asarray(scene[name])
            self.assertAlmostEqual(np.ptp(points[:,0]),np.ptp(points[:,1]),places=3)
        np.testing.assert_allclose(scene["upperLidClosedPts"],
                                   list(reversed(scene["lowerLidClosedPts"])),atol=1e-6)
        tree = np.asarray(Image.open(ROOT / "eyes/graphics/stained-glass/tree.png"))
        self.assertEqual(tree.shape[2],4)
        self.assertEqual(int(tree[0,0,3]),0)
        data = np.asarray(Image.open(ROOT / "eyes/graphics/stained-glass/tree-panes.png"))
        self.assertGreater(len(np.unique(data.reshape(-1,3),axis=0)),40)
        self.assertGreater(np.count_nonzero(data[:,:,2]),data.shape[0]*data.shape[1]*0.25)

    def test_tree_projection_options(self):
        args = theme_options(["--theme","stained-glass","--tree-y","-25",
                              "--tree-scale","0.8","--tree-every","5","15"])
        self.assertEqual(args.tree_y,-25)
        self.assertEqual(args.tree_scale,0.8)
        self.assertEqual(args.tree_every,[5,15])


if __name__ == "__main__":
    unittest.main()
