#include std_head_fs.inc
varying vec2 texcoordout;
void main(void) {
  // Every pixel is glass. The eye is a pattern within an opaque pane,
  // including the closed eyelid; no black eye-shaped masking planes.
  vec2 uv = texcoordout;
  vec2 p = (uv - 0.5) * vec2(unif[17].y, unif[17].z);
  // A single inverse deformation carries the glass, leading, lids and iris.
  // Anchor the perimeter to the physical window while the interior flows.
  vec2 border = 2.0 * uv - 1.0;
  vec2 b2 = border * border;
  float anchor = (1.0-b2.x*b2.x) * (1.0-b2.y*b2.y);
  float flow = anchor * (0.30 + 0.70 * exp(-0.30 * dot(p,p)));
  vec2 rest = p - unif[16].xy * flow;
  float blink = clamp(unif[17].x,0.0,1.0);
  rest.y += 0.38 * blink * p.y / sqrt(0.04+p.y*p.y)
            * exp(-0.60*abs(p.y)) * anchor;
  rest += 0.08 * (unif[16].z-0.5) * p / sqrt(0.10+dot(p,p)) * flow;
  p = rest;
  // Radial glass courses converge on the iris like the reference's star
  // windows. Both blue and gold panes share the same angular coordinates.
  float angle = atan(p.y,p.x) / 6.2831853 + 0.5;
  float radius = length(p);
  vec2 materialUV = vec2(angle+unif[18].y, log(1.0+radius*1.8)*0.60);
  vec3 glass = texture2D(tex0, materialUV).rgb;
  float x = abs(p.x);
  float halfHeight = 0.53 * pow(max(0.0, 1.0 - x*x), 0.65)
                     * (1.0 - blink);
  float edge = abs(p.y) - halfHeight;
  float withinX = 1.0 - smoothstep(0.98, 1.0, x);
  float inside = (1.0 - smoothstep(-0.008, 0.008, edge)) * withinX;
  vec3 eyeGlass = glass;
  float r = radius;
  float pupil = mix(0.14, 0.27, clamp(unif[16].z, 0.0, 1.0));
  float radial = clamp((r-pupil)/(0.52-pupil), 0.0, 1.0);
  vec3 iris = texture2D(tex1, vec2(angle,radial)).rgb;
  float irisMask = 1.0 - smoothstep(0.51,0.53,r);
  eyeGlass = mix(eyeGlass,iris,irisMask);
  vec3 darkGlass = glass * vec3(0.10,0.12,0.25);
  eyeGlass = mix(eyeGlass,darkGlass,1.0-smoothstep(pupil-0.008,pupil+0.008,r));
  float circleLead = max(1.0-smoothstep(0.009,0.021,abs(r-0.52)),
                        1.0-smoothstep(0.007,0.017,abs(r-pupil)));
  eyeGlass = mix(eyeGlass,vec3(0.006,0.008,0.018),circleLead);
  vec3 colour = mix(glass,eyeGlass,inside);
  float lidLead = (1.0-smoothstep(0.009,0.023,abs(edge))) * withinX;
  colour = mix(colour,vec3(0.006,0.008,0.018),lidLead);
  gl_FragColor = vec4(mix(glass,colour,unif[18].x),1.0);
}
