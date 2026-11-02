#include std_head_fs.inc
varying vec2 texcoordout;
void main(void) {
#include std_main_uv.inc
  // data: random phase, pane centre Y, valid pane. All pixels within a
  // pane share the same gain; the black leading remains black.
  vec3 pane = texture2D(tex1, texcoordout).rgb;
  float shimmer = 0.045 * sin(unif[16].x * 0.5 + pane.r * 6.2831853);
  float waveY = 1.12 - 1.24 * unif[16].z;
  float d = (pane.g - waveY) / 0.16;
  float sweep = exp(-d * d) * unif[16].y;
  float star = (1.0 - step(0.21, pane.g)) * unif[16].y
               * smoothstep(0.50, 0.85, unif[16].z);
  float animated = 0.73 + shimmer + 0.22 * sweep + 0.22 * star;
  float gain = mix(mix(0.36, 1.0, unif[17].y), animated, unif[17].x);
  // No additive whitening: preserve the saturated glass colours and outlines.
  texc.rgb *= mix(0.73, clamp(gain, 0.0, 1.0), step(0.5, pane.b));
  gl_FragColor = vec4(texc.rgb, texc.a * unif[5][2]);
}
