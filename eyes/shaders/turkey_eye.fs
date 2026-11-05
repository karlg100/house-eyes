#include std_head_fs.inc
varying vec2 texcoordout;
void main(void) {
  vec2 uv = texcoordout;
  vec2 p = (uv-0.5)*vec2(2.6,2.4);
  float silhouette = length(p/vec2(1.26,1.14));
  float alpha = 1.0-smoothstep(0.88,1.0,silhouette);
  if (alpha <= 0.0035) discard;
  float blink = clamp(unif[17].x,0.0,1.0);
  float follow = exp(-0.80*dot(p,p));
  vec2 skinUV = uv - unif[16].xy*0.06*follow;
  skinUV.y += 0.06*blink*p.y/sqrt(0.04+p.y*p.y)*follow;
  skinUV.x = mix(skinUV.x,1.0-skinUV.x,unif[17].y);
  vec3 skin = texture2D(tex0,clamp(skinUV,0.0,1.0)).rgb;
  skin *= 1.0-0.15*silhouette*silhouette;
  // Broad rounded bird eye, with the coloured skin itself forming the lid.
  vec2 lid = p-unif[16].xy*0.15;
  float lidX = lid.x/0.82;
  float halfHeight = 0.65*pow(max(0.0,1.0-lidX*lidX),0.45)*(1.0-blink);
  float edge = abs(lid.y)-halfHeight;
  float extent = 1.0-smoothstep(0.79,0.83,abs(lid.x));
  float opening = (1.0-smoothstep(-0.008,0.012,edge))*extent;
  vec2 q = p-unif[16].xy;
  float r = length(q);
  float pupil = mix(0.17,0.26,clamp(unif[16].z,0.0,1.0));
  float angle = atan(q.y,q.x)/6.2831853+0.5;
  float radial = clamp((r-pupil)/(0.60-pupil),0.0,1.0);
  vec3 iris = texture2D(tex1,vec2(angle,radial)).rgb*vec3(1.38,1.13,0.95);
  float irisMask = 1.0-smoothstep(0.57,0.61,r);
  vec3 eye = mix(vec3(0.065,0.040,0.025),iris,irisMask);
  eye = mix(eye,vec3(0.008,0.006,0.004),1.0-smoothstep(pupil-0.007,pupil+0.007,r));
  eye *= 0.90+0.10*sqrt(max(0.0,1.0-r*r));
  float shine = exp(-2.0*dot((q-vec2(-0.17,-0.19))/vec2(0.10,0.055),
                            (q-vec2(-0.17,-0.19))/vec2(0.10,0.055)));
  float pin = exp(-2.0*dot((q-vec2(-0.04,-0.11))/vec2(0.025),
                          (q-vec2(-0.04,-0.11))/vec2(0.025)));
  eye = mix(eye,vec3(1.0,0.97,0.88),clamp(0.90*shine+0.60*pin,0.0,1.0));
  vec3 colour = mix(skin,eye,opening);
  float rim = (1.0-smoothstep(0.008,0.030,abs(edge)))*extent;
  colour = mix(colour,skin*0.48,rim);
  gl_FragColor = vec4(colour,alpha*unif[5][2]);
}
