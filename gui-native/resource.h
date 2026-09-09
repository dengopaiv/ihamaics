/* resource.h - control and resource identifiers for the SAM GUI. */

#ifndef SAM_GUI_RESOURCE_H
#define SAM_GUI_RESOURCE_H

/* Resources */
#define IDR_CMUDICT       101

/* Controls */
#define IDC_TEXTLABEL     1000
#define IDC_TEXT          1001
#define IDC_PHONEMEMODE   1002
#define IDC_SPEEDLABEL    1003
#define IDC_SPEED         1004
#define IDC_SPEEDSPIN     1005
#define IDC_PITCHLABEL    1006
#define IDC_PITCH         1007
#define IDC_PITCHSPIN     1008
#define IDC_MOUTHLABEL    1009
#define IDC_MOUTH         1010
#define IDC_MOUTHSPIN     1011
#define IDC_THROATLABEL   1012
#define IDC_THROAT        1013
#define IDC_THROATSPIN    1014
#define IDC_INFLLABEL     1015
#define IDC_INFL          1016
#define IDC_INFLSPIN      1017
#define IDC_PREVIEW       1018
#define IDC_CONVERT       1019
#define IDC_RENDER        1020
#define IDC_SINGMODE      1021
#define IDC_PRESETLABEL   1022
#define IDC_PRESET        1023

/* Private messages, posted from the playback thread. */
#define WM_APP_PLAY_DONE     (WM_APP + 1)
#define WM_APP_SYNTH_FAILED  (WM_APP + 2)

#endif /* SAM_GUI_RESOURCE_H */
