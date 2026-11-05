"""Turkey eye skin and centre beak for the three-window projection."""
import math


class TurkeyDecor:
    def __init__(self, pi3d, radius, spacing, options):
        skin = pi3d.Texture("graphics/thanksgiving/skin.png", mipmap=False,
                            filter=pi3d.constants.GL_LINEAR)
        # The existing brown unwrapped iris is shared with the reindeer skin.
        iris = pi3d.Texture("graphics/christmas/iris.png", mipmap=False,
                            filter=pi3d.constants.GL_LINEAR)
        shader = pi3d.Shader("shaders/turkey_eye")
        self.eyes = []
        for side, x in enumerate((-spacing, spacing)):
            eye = pi3d.Sprite(w=2.6*radius, h=2.4*radius, x=x, z=-radius-43)
            eye.set_draw_details(shader, [skin, iris])
            eye.set_custom_data(48, (0,0,0.5,0,float(side),0))
            self.eyes.append(eye)
        beak = pi3d.Texture("graphics/thanksgiving/beak.png", mipmap=False,
                            filter=pi3d.constants.GL_LINEAR, blend=True)
        width = 2.05*radius*options.beak_scale
        self.beak = pi3d.Sprite(w=width, h=width*beak.iy/beak.ix, x=0,
                                y=-0.45*radius+options.beak_y, z=-radius-44)
        self.beak.set_draw_details(pi3d.Shader("uv_flat"), [beak])

    def draw(self, left_rotation, right_rotation, pupil, left_blink, right_blink):
        for eye, rotation, blink in zip(self.eyes, (left_rotation,right_rotation),
                                        (left_blink,right_blink)):
            rx,ry = map(math.radians,rotation)
            eye.set_custom_data(48,(-0.65*math.sin(ry),-0.50*math.sin(rx),pupil,blink))
            eye.draw()
        self.beak.draw()
