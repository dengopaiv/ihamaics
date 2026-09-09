/*
 * sam_gui.cpp - SAM desktop GUI, Win32, no Python.
 *
 * Reproduces sam_gui.py feature for feature against the C engine in
 * native/ rather than the Python package, and adds the phoneme mode and
 * Convert button that the engine has always supported through
 * text_to_audio(phonetic=True) but no GUI exposed. The whole thing -
 * renderer, parser, reciter and the 3.6 MB CMU dictionary as a resource -
 * links into one executable with the static CRT, so it runs on a bare
 * Windows with nothing installed first.
 *
 * Plain Win32 controls throughout, deliberately. Every control is a
 * standard one with a static label immediately before it in tab order
 * and an & accelerator, which is what screen readers expect; a custom
 * drawn UI would look the same and be unusable. This program is a front
 * end for a screen reader voice, so that is not a detail.
 */

#define WIN32_LEAN_AND_MEAN
#define _CRT_SECURE_NO_WARNINGS

#include <windows.h>
#include <commctrl.h>
#include <commdlg.h>
#include <mmsystem.h>
#include <shellapi.h>   /* CommandLineToArgvW; WIN32_LEAN_AND_MEAN drops it */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wctype.h>

extern "C" {
#include "sam_text.h"
}

#include "resource.h"

/* /MT pulls in the CRT but not the UI libraries, so name them here rather
 * than spreading the link line across the build script. */
#pragma comment(lib, "user32.lib")
#pragma comment(lib, "gdi32.lib")
#pragma comment(lib, "comctl32.lib")
#pragma comment(lib, "winmm.lib")
#pragma comment(lib, "comdlg32.lib")
#pragma comment(lib, "shell32.lib")

/* --------------------------------------------------------------------- */
/* Defaults and ranges, matching sam_gui.py                              */
/* --------------------------------------------------------------------- */

/*
 * One row per voice parameter. sam_gui.py builds five near-identical
 * spin controls; describing them once keeps the ranges, the defaults and
 * the tab order in a single place where they can be read against the
 * Python at a glance.
 *
 * Speed starts at 1, not 0: speed == 0 divides by zero in the renderer,
 * which is why sam_render returns SAM_E_BADSPEED for it.
 */
struct ParamSpec {
    const wchar_t *label;
    int lo, hi, def;
    int labelId, editId, spinId;
};

static const ParamSpec PARAMS[] = {
    { L"&Speed:",      1, 255,  72, IDC_SPEEDLABEL,  IDC_SPEED,  IDC_SPEEDSPIN  },
    { L"&Pitch:",      0, 255,  64, IDC_PITCHLABEL,  IDC_PITCH,  IDC_PITCHSPIN  },
    { L"Mo&uth:",      0, 255, 128, IDC_MOUTHLABEL,  IDC_MOUTH,  IDC_MOUTHSPIN  },
    { L"T&hroat:",     0, 255, 128, IDC_THROATLABEL, IDC_THROAT, IDC_THROATSPIN },
    { L"&Inflection:", 0, 100,  50, IDC_INFLLABEL,   IDC_INFL,   IDC_INFLSPIN   },
};

#define PARAM_COUNT ((int)(sizeof(PARAMS) / sizeof(PARAMS[0])))

enum { P_SPEED = 0, P_PITCH, P_MOUTH, P_THROAT, P_INFLECTION };

static const wchar_t *DEFAULT_TEXT = L"Hello, my name is Sam.";
static const wchar_t *WINDOW_TITLE = L"SAM Text-to-Speech";

/* --------------------------------------------------------------------- */
/* Globals                                                               */
/* --------------------------------------------------------------------- */

static HINSTANCE g_inst;
static HWND g_main, g_textLabel, g_text, g_phonemeMode;
static HWND g_edit[PARAM_COUNT], g_spin[PARAM_COUNT];
static HWND g_preview, g_convert, g_render;
static HFONT g_font;

static const void *g_dict;      /* into the resource; process-lifetime */
static int g_dictLen;

static volatile LONG g_playing;

/* --------------------------------------------------------------------- */
/* Small helpers                                                         */
/* --------------------------------------------------------------------- */

static void ShowError(const wchar_t *msg, const wchar_t *title)
{
    MessageBoxW(g_main, msg, title, MB_OK | MB_ICONERROR);
}

static void ShowWarn(const wchar_t *msg, const wchar_t *title)
{
    MessageBoxW(g_main, msg, title, MB_OK | MB_ICONWARNING);
}

/*
 * The engine speaks bytes, the UI holds UTF-16. Everything the reciter
 * and dictionary understand is ASCII, so anything outside it would be
 * dropped by the reciter anyway; CP_ACP keeps the mapping predictable
 * for the Latin-1 range the Python side also accepted.
 */
static char *WideToBytes(const wchar_t *w)
{
    int n = WideCharToMultiByte(CP_ACP, 0, w, -1, NULL, 0, NULL, NULL);
    char *s;

    if (n <= 0) {
        return NULL;
    }
    s = (char *)malloc((size_t)n);
    if (s == NULL) {
        return NULL;
    }
    if (WideCharToMultiByte(CP_ACP, 0, w, -1, s, n, NULL, NULL) <= 0) {
        free(s);
        return NULL;
    }
    return s;
}

static wchar_t *BytesToWide(const char *s)
{
    int n = MultiByteToWideChar(CP_ACP, 0, s, -1, NULL, 0);
    wchar_t *w;

    if (n <= 0) {
        return NULL;
    }
    w = (wchar_t *)malloc((size_t)n * sizeof(wchar_t));
    if (w == NULL) {
        return NULL;
    }
    if (MultiByteToWideChar(CP_ACP, 0, s, -1, w, n) <= 0) {
        free(w);
        return NULL;
    }
    return w;
}

/* Window text as a freshly allocated wide string; caller frees. */
static wchar_t *GetText(HWND hwnd)
{
    int n = GetWindowTextLengthW(hwnd);
    wchar_t *buf = (wchar_t *)malloc(((size_t)n + 1) * sizeof(wchar_t));

    if (buf == NULL) {
        return NULL;
    }
    GetWindowTextW(hwnd, buf, n + 1);
    buf[n] = L'\0';
    return buf;
}

static void TrimInPlace(wchar_t *s)
{
    wchar_t *start = s, *end;

    while (*start && iswspace(*start)) {
        start++;
    }
    if (start != s) {
        memmove(s, start, (wcslen(start) + 1) * sizeof(wchar_t));
    }
    end = s + wcslen(s);
    while (end > s && iswspace(end[-1])) {
        *--end = L'\0';
    }
}

static int GetSpin(int which)
{
    return (int)SendMessageW(g_spin[which], UDM_GETPOS32, 0, 0);
}

static int IsChecked(HWND cb)
{
    return SendMessageW(cb, BM_GETCHECK, 0, 0) == BST_CHECKED;
}

/* --------------------------------------------------------------------- */
/* Synthesis                                                             */
/* --------------------------------------------------------------------- */

/*
 * Voice settings exactly as sam_gui.py builds them: the five spin values,
 * and sing mode off because that GUI has no control for it and
 * text_to_wav defaults singmode to False.
 */
static sam_voice_t VoiceFrom(int speed, int pitch, int mouth, int throat,
                             int inflection)
{
    sam_voice_t v;

    v.pitch = (unsigned char)pitch;
    v.mouth = (unsigned char)mouth;
    v.throat = (unsigned char)throat;
    v.speed = (unsigned char)speed;
    v.singmode = 0;
    v.inflection = inflection;
    return v;
}

static sam_voice_t VoiceFromUI(void)
{
    return VoiceFrom(GetSpin(P_SPEED), GetSpin(P_PITCH), GetSpin(P_MOUTH),
                     GetSpin(P_THROAT), GetSpin(P_INFLECTION));
}

/* Render to 8-bit unsigned PCM. Returns a malloc'd buffer and its length. */
static unsigned char *Synthesize(const char *input, int phonemeMode,
                                 const sam_voice_t *v, int *outSamples)
{
    unsigned char *pcm;
    int need, got;

    if (phonemeMode) {
        need = sam_speak_phonemes(input, v, NULL, 0);
    } else {
        need = sam_speak_text(input, g_dict, g_dictLen, v, NULL, 0);
    }
    if (need <= 0) {
        return NULL;
    }

    pcm = (unsigned char *)malloc((size_t)need);
    if (pcm == NULL) {
        return NULL;
    }

    if (phonemeMode) {
        got = sam_speak_phonemes(input, v, pcm, need);
    } else {
        got = sam_speak_text(input, g_dict, g_dictLen, v, pcm, need);
    }
    if (got <= 0) {
        free(pcm);
        return NULL;
    }
    *outSamples = got;
    return pcm;
}

/*
 * Wrap PCM in a RIFF/WAVE header. Returns a malloc'd buffer.
 *
 * 8-bit unsigned mono at 22050 Hz, which is what the renderer produces
 * and what audio_to_wav() in sam.py writes. Byte rate and block align
 * are therefore 22050 and 1.
 */
static unsigned char *MakeWav(const unsigned char *pcm, int samples,
                              DWORD *outLen)
{
    const DWORD dataSize = (DWORD)samples;
    const DWORD total = 44 + dataSize;
    unsigned char *w = (unsigned char *)malloc(total);
    DWORD v;

    if (w == NULL) {
        return NULL;
    }
    memcpy(w, "RIFF", 4);
    v = dataSize + 36;         memcpy(w + 4, &v, 4);
    memcpy(w + 8, "WAVEfmt ", 8);
    v = 16;                    memcpy(w + 16, &v, 4);
    { WORD f = 1;              memcpy(w + 20, &f, 2); }   /* PCM */
    { WORD ch = 1;             memcpy(w + 22, &ch, 2); }
    v = SAM_SAMPLE_RATE;       memcpy(w + 24, &v, 4);
    v = SAM_SAMPLE_RATE;       memcpy(w + 28, &v, 4);     /* byte rate */
    { WORD ba = 1;             memcpy(w + 32, &ba, 2); }
    { WORD bits = 8;           memcpy(w + 34, &bits, 2); }
    memcpy(w + 36, "data", 4);
    memcpy(w + 40, &dataSize, 4);
    memcpy(w + 44, pcm, dataSize);

    *outLen = total;
    return w;
}

static int WriteWholeFile(const wchar_t *path, const void *data, DWORD len)
{
    DWORD written = 0;
    HANDLE f = CreateFileW(path, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS,
                           FILE_ATTRIBUTE_NORMAL, NULL);

    if (f == INVALID_HANDLE_VALUE) {
        return 0;
    }
    if (!WriteFile(f, data, len, &written, NULL) || written != len) {
        CloseHandle(f);
        return 0;
    }
    CloseHandle(f);
    return 1;
}

/* --------------------------------------------------------------------- */
/* Preview, on a worker thread                                           */
/* --------------------------------------------------------------------- */

struct PlayJob {
    char       *input;
    int         phonemeMode;
    sam_voice_t voice;
};

static DWORD WINAPI PlayThread(LPVOID param)
{
    PlayJob *job = (PlayJob *)param;
    int samples = 0;
    unsigned char *pcm = Synthesize(job->input, job->phonemeMode,
                                    &job->voice, &samples);

    if (pcm != NULL) {
        DWORD wavLen = 0;
        unsigned char *wav = MakeWav(pcm, samples, &wavLen);
        free(pcm);
        if (wav != NULL) {
            /* Synchronous on this thread, so the buffer outlives playback
             * and a second Preview cannot pull it out from underneath. */
            PlaySoundW((LPCWSTR)wav, NULL, SND_MEMORY | SND_SYNC);
            free(wav);
        }
    } else {
        PostMessageW(g_main, WM_APP_SYNTH_FAILED, 0, 0);
    }

    free(job->input);
    delete job;
    InterlockedExchange(&g_playing, 0);
    PostMessageW(g_main, WM_APP_PLAY_DONE, 0, 0);
    return 0;
}

static void OnPreview(void)
{
    wchar_t *w = GetText(g_text);
    char *input;
    PlayJob *job;
    HANDLE th;

    if (w == NULL) {
        return;
    }
    TrimInPlace(w);
    if (w[0] == L'\0') {
        free(w);
        ShowWarn(L"Please enter some text to speak.", L"No Text");
        return;
    }
    if (InterlockedCompareExchange(&g_playing, 1, 0) != 0) {
        free(w);
        return;   /* already speaking */
    }

    input = WideToBytes(w);
    free(w);
    if (input == NULL) {
        InterlockedExchange(&g_playing, 0);
        return;
    }

    job = new PlayJob;
    job->input = input;
    job->phonemeMode = IsChecked(g_phonemeMode);
    /* Read the controls on the UI thread; the worker must not touch them. */
    job->voice = VoiceFromUI();

    EnableWindow(g_preview, FALSE);
    th = CreateThread(NULL, 0, PlayThread, job, 0, NULL);
    if (th == NULL) {
        EnableWindow(g_preview, TRUE);
        InterlockedExchange(&g_playing, 0);
        free(job->input);
        delete job;
        return;
    }
    CloseHandle(th);
}

/* --------------------------------------------------------------------- */
/* Convert to phonemes                                                   */
/* --------------------------------------------------------------------- */

static void OnConvert(void)
{
    wchar_t *w = GetText(g_text);
    char *input, *out;
    int cap, n;

    if (w == NULL) {
        return;
    }
    TrimInPlace(w);
    if (w[0] == L'\0') {
        free(w);
        ShowWarn(L"Please enter some text.", L"No Text");
        return;
    }

    input = WideToBytes(w);
    free(w);
    if (input == NULL) {
        return;
    }

    /* Ask the engine how much room the answer needs rather than guessing:
     * a dictionary pronunciation can be several times the word. */
    n = sam_text_to_phonemes(input, g_dict, g_dictLen, NULL, 0);
    if (n < 0) {
        free(input);
        ShowError(L"Conversion failed.", L"Error");
        return;
    }
    cap = n + 1;
    out = (char *)malloc((size_t)cap);
    if (out == NULL) {
        free(input);
        return;
    }

    n = sam_text_to_phonemes(input, g_dict, g_dictLen, out, cap);
    free(input);

    if (n >= 0) {
        wchar_t *wout = BytesToWide(out);
        if (wout != NULL) {
            SetWindowTextW(g_text, wout);
            free(wout);
            SendMessageW(g_phonemeMode, BM_SETCHECK, BST_CHECKED, 0);
            SetWindowTextW(g_textLabel, L"&Phonemes to speak:");
            SetFocus(g_text);
        }
    } else {
        ShowError(L"Conversion failed.", L"Error");
    }
    free(out);
}

/* --------------------------------------------------------------------- */
/* Render to WAV                                                         */
/* --------------------------------------------------------------------- */

static void OnRender(void)
{
    wchar_t *w = GetText(g_text);
    wchar_t path[MAX_PATH] = L"speech.wav";
    OPENFILENAMEW ofn;
    sam_voice_t voice;
    char *input;
    unsigned char *pcm, *wav;
    DWORD wavLen = 0;
    int samples = 0;

    if (w == NULL) {
        return;
    }
    TrimInPlace(w);
    if (w[0] == L'\0') {
        free(w);
        ShowWarn(L"Please enter some text to speak.", L"No Text");
        return;
    }

    ZeroMemory(&ofn, sizeof(ofn));
    ofn.lStructSize = sizeof(ofn);
    ofn.hwndOwner = g_main;
    ofn.lpstrFilter = L"WAV files (*.wav)\0*.wav\0All files\0*.*\0";
    ofn.lpstrFile = path;
    ofn.nMaxFile = MAX_PATH;
    ofn.lpstrTitle = L"Save WAV file";
    ofn.lpstrDefExt = L"wav";
    ofn.Flags = OFN_OVERWRITEPROMPT | OFN_PATHMUSTEXIST | OFN_EXPLORER;

    if (!GetSaveFileNameW(&ofn)) {
        free(w);
        return;   /* cancelled */
    }

    input = WideToBytes(w);
    free(w);
    if (input == NULL) {
        return;
    }

    voice = VoiceFromUI();
    pcm = Synthesize(input, IsChecked(g_phonemeMode), &voice, &samples);
    free(input);
    if (pcm == NULL) {
        ShowError(L"Failed to synthesize audio.", L"Error");
        return;
    }

    wav = MakeWav(pcm, samples, &wavLen);
    free(pcm);
    if (wav == NULL) {
        ShowError(L"Out of memory.", L"Error");
        return;
    }

    if (!WriteWholeFile(path, wav, wavLen)) {
        free(wav);
        ShowError(L"Could not write the file.", L"Error");
        return;
    }
    free(wav);

    {
        wchar_t msg[MAX_PATH + 64];
        _snwprintf(msg, MAX_PATH + 63, L"Saved to %s", path);
        msg[MAX_PATH + 63] = L'\0';
        MessageBoxW(g_main, msg, L"Success", MB_OK | MB_ICONINFORMATION);
    }
}

/* --------------------------------------------------------------------- */
/* Layout                                                                */
/* --------------------------------------------------------------------- */

static HWND Make(const wchar_t *cls, const wchar_t *text, DWORD style,
                 int x, int y, int w, int h, int id)
{
    HWND c = CreateWindowExW(0, cls, text, WS_CHILD | WS_VISIBLE | style,
                             x, y, w, h, g_main, (HMENU)(INT_PTR)id,
                             g_inst, NULL);
    if (c != NULL) {
        SendMessageW(c, WM_SETFONT, (WPARAM)g_font, TRUE);
    }
    return c;
}

/*
 * A multiline EDIT answers WM_GETDLGCODE with DLGC_WANTALLKEYS, meaning
 * "give me every key and do not interpret any of them". IsDialogMessage
 * honours that by returning early - before it reaches its own VK_TAB
 * handling - so Tab is delivered to the edit control, which inserts a
 * tab character. Focus goes into the text box and cannot get out.
 *
 * That is a keyboard trap. In a program whose whole purpose is a screen
 * reader voice it is the worst kind, because the people most likely to
 * meet it are the people least able to reach for the mouse instead.
 *
 * So the control keeps DLGC_WANTALLKEYS for everything except a Tab
 * keydown, where it stands aside and lets the dialog manager move the
 * focus. Enter still inserts a newline (ES_WANTRETURN), the arrow keys
 * still navigate the text, and typing is untouched: the answer is only
 * changed for the one key being asked about, which is why WM_GETDLGCODE
 * carries the message it is asking on behalf of.
 *
 * The tab character is not worth keeping. This box holds a sentence to
 * be spoken aloud, and a tab in it is silent.
 */
static WNDPROC g_textProc;

static LRESULT CALLBACK TextProc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp)
{
    LRESULT code;
    const MSG *m;

    if (msg == WM_GETDLGCODE) {
        code = CallWindowProcW(g_textProc, hwnd, msg, wp, lp);
        m = (const MSG *)lp;
        if (m != NULL && m->message == WM_KEYDOWN && m->wParam == VK_TAB) {
            /* DLGC_WANTMESSAGE is the same bit as DLGC_WANTALLKEYS. */
            code &= ~(LRESULT)(DLGC_WANTALLKEYS | DLGC_WANTTAB);
        }
        return code;
    }
    return CallWindowProcW(g_textProc, hwnd, msg, wp, lp);
}

static HWND MakeSpin(HWND buddy, int lo, int hi, int value, int id)
{
    HWND s = CreateWindowExW(0, UPDOWN_CLASSW, NULL,
                             WS_CHILD | WS_VISIBLE | UDS_SETBUDDYINT
                             | UDS_ALIGNRIGHT | UDS_ARROWKEYS | UDS_NOTHOUSANDS,
                             0, 0, 0, 0, g_main, (HMENU)(INT_PTR)id,
                             g_inst, NULL);
    if (s != NULL) {
        SendMessageW(s, UDM_SETBUDDY, (WPARAM)buddy, 0);
        SendMessageW(s, UDM_SETRANGE32, lo, hi);
        SendMessageW(s, UDM_SETPOS32, 0, value);
    }
    return s;
}

static void CreateControls(void)
{
    const int M = 12;            /* margin */
    const int W = 430;           /* client width used for layout */
    const int LBL = 20, ROW = 26, GAP = 8;
    const int labW = 90, edW = 70;
    int y = M;
    int i;

    g_textLabel = Make(L"STATIC", L"&Text to speak:", 0,
                       M, y, W - 2 * M, LBL, IDC_TEXTLABEL);
    y += LBL + 2;

    g_text = CreateWindowExW(WS_EX_CLIENTEDGE, L"EDIT", DEFAULT_TEXT,
                             WS_CHILD | WS_VISIBLE | WS_TABSTOP | WS_VSCROLL
                             | ES_MULTILINE | ES_AUTOVSCROLL | ES_WANTRETURN,
                             M, y, W - 2 * M, 110, g_main,
                             (HMENU)(INT_PTR)IDC_TEXT, g_inst, NULL);
    SendMessageW(g_text, WM_SETFONT, (WPARAM)g_font, TRUE);
    g_textProc = (WNDPROC)(LONG_PTR)SetWindowLongPtrW(
        g_text, GWLP_WNDPROC, (LONG_PTR)TextProc);
    y += 110 + GAP;

    g_phonemeMode = Make(L"BUTTON", L"Phoneme &mode (input is raw phonemes)",
                         BS_AUTOCHECKBOX | WS_TABSTOP,
                         M, y, W - 2 * M, LBL, IDC_PHONEMEMODE);
    y += LBL + GAP;

    for (i = 0; i < PARAM_COUNT; i++) {
        const ParamSpec *p = &PARAMS[i];
        wchar_t buf[16];

        /* The label goes in immediately before its edit, so the screen
         * reader announces the two together and tab order is sensible. */
        Make(L"STATIC", p->label, SS_RIGHT, M, y + 4, labW, LBL, p->labelId);

        _snwprintf(buf, 15, L"%d", p->def);
        buf[15] = L'\0';
        g_edit[i] = CreateWindowExW(WS_EX_CLIENTEDGE, L"EDIT", buf,
                                    WS_CHILD | WS_VISIBLE | WS_TABSTOP
                                    | ES_NUMBER, M + labW + GAP, y, edW, 23,
                                    g_main, (HMENU)(INT_PTR)p->editId,
                                    g_inst, NULL);
        SendMessageW(g_edit[i], WM_SETFONT, (WPARAM)g_font, TRUE);
        g_spin[i] = MakeSpin(g_edit[i], p->lo, p->hi, p->def, p->spinId);
        y += ROW + 4;
    }

    y += GAP - 4;

    {
        const int bh = 28, bgap = 8;
        int bx = M;

        g_preview = Make(L"BUTTON", L"Pre&view",
                         BS_DEFPUSHBUTTON | WS_TABSTOP, bx, y, 90, bh,
                         IDC_PREVIEW);
        bx += 90 + bgap;
        g_convert = Make(L"BUTTON", L"&Convert to Phonemes",
                         BS_PUSHBUTTON | WS_TABSTOP, bx, y, 150, bh,
                         IDC_CONVERT);
        bx += 150 + bgap;
        g_render = Make(L"BUTTON", L"Render to &WAV",
                        BS_PUSHBUTTON | WS_TABSTOP, bx, y, 120, bh,
                        IDC_RENDER);
    }
}

/* --------------------------------------------------------------------- */
/* Window procedure                                                      */
/* --------------------------------------------------------------------- */

static LRESULT CALLBACK WndProc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp)
{
    switch (msg) {
    case WM_CREATE:
        g_main = hwnd;
        CreateControls();
        SetFocus(g_text);
        return 0;

    case WM_COMMAND:
        switch (LOWORD(wp)) {
        case IDC_PREVIEW:
            OnPreview();
            return 0;
        case IDC_CONVERT:
            OnConvert();
            return 0;
        case IDC_RENDER:
            OnRender();
            return 0;
        case IDC_PHONEMEMODE:
            if (HIWORD(wp) == BN_CLICKED) {
                SetWindowTextW(g_textLabel,
                               IsChecked(g_phonemeMode)
                               ? L"&Phonemes to speak:"
                               : L"&Text to speak:");
            }
            return 0;
        case IDCANCEL:
            DestroyWindow(hwnd);
            return 0;
        }
        break;

    case WM_APP_PLAY_DONE:
        EnableWindow(g_preview, TRUE);
        return 0;

    case WM_APP_SYNTH_FAILED:
        ShowError(L"Failed to synthesize audio.", L"Error");
        return 0;

    case WM_CTLCOLORSTATIC:
        /* Let the labels sit on the dialog background rather than white. */
        SetBkMode((HDC)wp, TRANSPARENT);
        return (LRESULT)GetSysColorBrush(COLOR_BTNFACE);

    case WM_CLOSE:
        DestroyWindow(hwnd);
        return 0;

    case WM_DESTROY:
        PostQuitMessage(0);
        return 0;
    }
    return DefWindowProcW(hwnd, msg, wp, lp);
}

/* --------------------------------------------------------------------- */
/* Startup                                                               */
/* --------------------------------------------------------------------- */

/* The dictionary lives in the executable; lock it once and keep the pointer. */
static int LoadDictResource(void)
{
    HRSRC res = FindResourceW(g_inst, MAKEINTRESOURCEW(IDR_CMUDICT), RT_RCDATA);
    HGLOBAL h;

    if (res == NULL) {
        return 0;
    }
    g_dictLen = (int)SizeofResource(g_inst, res);
    h = LoadResource(g_inst, res);
    if (h == NULL) {
        return 0;
    }
    g_dict = LockResource(h);
    return g_dict != NULL && g_dictLen > 0;
}

static void MakeFont(void)
{
    NONCLIENTMETRICSW ncm;

    ZeroMemory(&ncm, sizeof(ncm));
    ncm.cbSize = sizeof(ncm);
    if (SystemParametersInfoW(SPI_GETNONCLIENTMETRICS, sizeof(ncm), &ncm, 0)) {
        g_font = CreateFontIndirectW(&ncm.lfMessageFont);
    }
    if (g_font == NULL) {
        g_font = (HFONT)GetStockObject(DEFAULT_GUI_FONT);
    }
}

/*
 * Headless self-test, so the shipped binary can be checked rather than a
 * separate harness that merely shares its sources.
 *
 *   sam_gui.exe --selftest SPEED PITCH MOUTH THROAT INFLECTION
 *               PHONEMEMODE OUT.WAV TEXT
 *
 * PHONEMEMODE is 0 or 1 and means exactly what the checkbox means.
 * Everything downstream is the same code the buttons run, VoiceFrom()
 * included, so a match against the Python GUI is a statement about this
 * executable and not about a copy of it. Returns 0 on success.
 * See native/tools/verify_gui.py.
 */
static int RunSelfTest(int argc, wchar_t **argv)
{
    sam_voice_t v;
    unsigned char *pcm, *wav;
    DWORD wavLen = 0;
    char *input;
    int phonemeMode, samples = 0;

    if (argc < 10) {
        return 2;
    }
    v = VoiceFrom(_wtoi(argv[2]), _wtoi(argv[3]), _wtoi(argv[4]),
                  _wtoi(argv[5]), _wtoi(argv[6]));
    phonemeMode = _wtoi(argv[7]);

    input = WideToBytes(argv[9]);
    if (input == NULL) {
        return 3;
    }

    pcm = Synthesize(input, phonemeMode, &v, &samples);
    free(input);
    if (pcm == NULL) {
        return 4;
    }

    wav = MakeWav(pcm, samples, &wavLen);
    free(pcm);
    if (wav == NULL) {
        return 5;
    }
    if (!WriteWholeFile(argv[8], wav, wavLen)) {
        free(wav);
        return 6;
    }
    free(wav);
    return 0;
}

int WINAPI wWinMain(HINSTANCE inst, HINSTANCE, LPWSTR, int show)
{
    WNDCLASSEXW wc;
    INITCOMMONCONTROLSEX icc;
    HWND hwnd;
    MSG msg;
    RECT r;

    g_inst = inst;

    icc.dwSize = sizeof(icc);
    icc.dwICC = ICC_UPDOWN_CLASS | ICC_STANDARD_CLASSES;
    InitCommonControlsEx(&icc);

    if (sam_abi_version() != SAM_ABI_VERSION
        || sam_text_abi_version() != SAM_TEXT_ABI_VERSION) {
        MessageBoxW(NULL, L"The speech engine is the wrong version.",
                    L"SAM", MB_OK | MB_ICONERROR);
        return 1;
    }
    if (!LoadDictResource()) {
        MessageBoxW(NULL,
                    L"The pronunciation dictionary is missing from this "
                    L"executable. Rebuild with native\\tools\\gen_dict.py "
                    L"having been run first.",
                    L"SAM", MB_OK | MB_ICONERROR);
        return 1;
    }

    {
        int argc = 0;
        wchar_t **argv = CommandLineToArgvW(GetCommandLineW(), &argc);
        if (argv != NULL) {
            if (argc >= 2 && wcscmp(argv[1], L"--selftest") == 0) {
                int rc = RunSelfTest(argc, argv);
                LocalFree(argv);
                return rc;
            }
            LocalFree(argv);
        }
    }

    MakeFont();

    ZeroMemory(&wc, sizeof(wc));
    wc.cbSize = sizeof(wc);
    wc.lpfnWndProc = WndProc;
    wc.hInstance = inst;
    wc.hCursor = LoadCursorW(NULL, IDC_ARROW);
    wc.hbrBackground = (HBRUSH)(COLOR_BTNFACE + 1);
    wc.lpszClassName = L"SAMMainWindow";
    wc.hIcon = LoadIconW(NULL, IDI_APPLICATION);
    wc.hIconSm = LoadIconW(NULL, IDI_APPLICATION);
    if (!RegisterClassExW(&wc)) {
        return 1;
    }

    r.left = 0;
    r.top = 0;
    r.right = 430;
    r.bottom = 400;
    AdjustWindowRect(&r, WS_OVERLAPPEDWINDOW & ~WS_THICKFRAME, FALSE);

    hwnd = CreateWindowExW(0, wc.lpszClassName, WINDOW_TITLE,
                           (WS_OVERLAPPEDWINDOW & ~WS_THICKFRAME
                            & ~WS_MAXIMIZEBOX),
                           CW_USEDEFAULT, CW_USEDEFAULT,
                           r.right - r.left, r.bottom - r.top,
                           NULL, NULL, inst, NULL);
    if (hwnd == NULL) {
        return 1;
    }

    ShowWindow(hwnd, show);
    UpdateWindow(hwnd);

    while (GetMessageW(&msg, NULL, 0, 0) > 0) {
        /* IsDialogMessage gives tab order, arrow keys within groups, the
         * & accelerators and the default button - everything a screen
         * reader user needs and none of which a bare loop provides. */
        if (!IsDialogMessageW(hwnd, &msg)) {
            TranslateMessage(&msg);
            DispatchMessageW(&msg);
        }
    }
    return (int)msg.wParam;
}
