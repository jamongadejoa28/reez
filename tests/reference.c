#include <stdlib.h>
#include <unistd.h>
#include <SDL2/SDL.h>
#include "lvgl.h"
#include "ui.h"
int main(int argc,char **argv){if(argc!=3)return 2;lv_init();lv_sdl_window_create(800,480);ui_init();loadScreen(atoi(argv[1]));for(int i=0;i<90;i++){lv_timer_handler();usleep(10000);}lv_draw_buf_t *b=lv_snapshot_take(lv_screen_active(),LV_COLOR_FORMAT_ARGB8888);if(!b)return 1;SDL_Surface *s=SDL_CreateRGBSurfaceWithFormatFrom(b->data,800,480,32,b->header.stride,SDL_PIXELFORMAT_ARGB8888);int result=SDL_SaveBMP(s,argv[2]);SDL_FreeSurface(s);lv_draw_buf_destroy(b);return result;}
