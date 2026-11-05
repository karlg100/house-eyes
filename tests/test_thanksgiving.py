"""Thanksgiving runtime rendering and controls, without GPIO or a GPU."""
from pathlib import Path
import sys
import types
import unittest

import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
sys.path.insert(0,str(ROOT/"eyes"))
from preview_christmas import load_scene,draw_scene,turkey_eye_colour
from seasonal import theme_options


class TurkeyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scene=load_scene("thanksgiving")

    def test_turkey_replaces_old_eyes_and_center_with_two_eyes_and_beak(self):
        scene=self.scene
        drawn=draw_scene(scene)
        turkey=scene["turkeyDecor"]
        self.assertEqual(len(drawn),3)
        self.assertEqual(drawn,turkey.eyes+[turkey.beak])
        for name in ("leftEye","rightEye","centerEye","centerIris","centerUpperEyelid","centerLowerEyelid"):
            self.assertNotIn(scene[name],drawn)
        self.assertIsNone(scene["decor"])
        self.assertIsNone(scene["glassDecor"])
        self.assertIsNone(scene["noseGlow"])
        self.assertIsNone(scene["treeGlow"])

    def test_tracker_controls_outer_eyes_and_pupils_but_not_beak(self):
        scene=self.scene
        scene["gazeInput"]=types.SimpleNamespace(get=lambda now:
            ([(.8,.2),(-1,-1),(-.8,-.2)],True,1.0))
        scene["lastFrameTime"]-=1
        draw_scene(scene)
        left,right=scene["turkeyDecor"].eyes
        self.assertGreater(left.custom_data[48],0)
        self.assertLess(right.custom_data[48],0)
        self.assertLess(left.custom_data[49],0)
        self.assertGreater(right.custom_data[49],0)
        self.assertGreater(left.custom_data[50],.5)
        beak=scene["turkeyDecor"].beak
        self.assertEqual((beak.rx,beak.ry),(0,0))
        self.assertEqual(beak.xyz[0],0)
        scene["gazeInput"]=None

    def test_blink_closes_with_skin_instead_of_black(self):
        eye=self.scene["turkeyDecor"].eyes[0]
        uv=np.array([[.5,.5],[0,0],[1,1]])
        opened,alpha=turkey_eye_colour(uv,*eye.textures,(0,0,.5,0,0,0))
        closed,closed_alpha=turkey_eye_colour(uv,*eye.textures,(0,0,.5,1,0,0))
        self.assertLess(opened[0].max(),5)
        self.assertGreater(closed[0].max(),40)
        np.testing.assert_allclose(alpha,closed_alpha)
        np.testing.assert_allclose(alpha,[1,0,0])

    def test_pupil_size_changes_and_all_gaze_extremes_remain_finite(self):
        eye=self.scene["turkeyDecor"].eyes[0]
        point=np.array([[.5+.22/2.6,.5]])
        small,_=turkey_eye_colour(point,*eye.textures,(0,0,0,0,0,0))
        large,_=turkey_eye_colour(point,*eye.textures,(0,0,1,0,0,0))
        self.assertGreater(small.max(),large.max()+10)
        uv=np.stack(np.meshgrid(np.linspace(0,1,12),np.linspace(0,1,12)),axis=-1)
        for gx,gy,blink in ((-.4,-.3,0),(.4,.3,.5),(0,0,1)):
            colour,alpha=turkey_eye_colour(uv,*eye.textures,(gx,gy,.5,blink,1,0))
            self.assertTrue(np.isfinite(colour).all())
            self.assertTrue(((alpha>=0)&(alpha<=1)).all())

    def test_beak_alignment_and_scale_options(self):
        scene=load_scene("thanksgiving",radius=100,extra=["--beak-y","-20","--beak-scale",".8"])
        beak=scene["turkeyDecor"].beak
        self.assertEqual(beak.xyz[1],-65)
        self.assertAlmostEqual(np.ptp(beak.buf[0].array_buffer[:,0]),164)
        args=theme_options(["--theme","thanksgiving"])
        self.assertEqual(args.beak_scale,1)
        self.assertEqual(args.beak_y,0)

    def test_runtime_artwork_has_transparent_beak(self):
        im=Image.open(ROOT/"eyes/graphics/thanksgiving/beak.png")
        self.assertEqual(im.mode,"RGBA")
        self.assertEqual(im.getextrema()[3],(0,255))
        eye=self.scene["turkeyDecor"].eyes[0]
        self.assertEqual(eye.textures[0].name,"graphics/thanksgiving/skin.png")
        self.assertEqual(eye.textures[1].name,"graphics/christmas/iris.png")


if __name__=="__main__":
    unittest.main()
