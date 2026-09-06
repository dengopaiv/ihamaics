#!/usr/bin/env python3
"""
SAM (Software Automatic Mouth) GUI Application
A wxPython GUI for the SAM text-to-speech synthesizer.
"""

import sys
import os
import winsound
import threading

# Add SAM module path
if getattr(sys, 'frozen', False):
    # Running as compiled exe
    base_path = sys._MEIPASS
    sys.path.insert(0, base_path)
else:
    # Running as script
    base_path = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.join(base_path, 'nvda-addon', 'synthDrivers', 'sam'))

import wx
from sam import text_to_wav


class SAMFrame(wx.Frame):
    """Main application frame."""

    def __init__(self):
        super().__init__(None, title="SAM Text-to-Speech", size=(400, 350))

        # Default parameter values
        self.defaults = {
            'speed': 72,
            'pitch': 64,
            'mouth': 128,
            'throat': 128,
            'inflection': 50
        }

        self.init_ui()
        self.Centre()

    def init_ui(self):
        """Initialize the user interface."""
        panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # Text input
        text_label = wx.StaticText(panel, label="Text to speak:")
        main_sizer.Add(text_label, flag=wx.LEFT | wx.TOP, border=10)

        self.text_ctrl = wx.TextCtrl(panel, style=wx.TE_MULTILINE, size=(-1, 80))
        self.text_ctrl.SetValue("Hello, my name is Sam.")
        main_sizer.Add(self.text_ctrl, proportion=1, flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=10)

        # Parameter spin controls (2 columns: label + spinctrl)
        param_sizer = wx.FlexGridSizer(rows=5, cols=2, hgap=10, vgap=8)
        param_sizer.AddGrowableCol(1)

        # Speed (0-255, default 72)
        speed_label = wx.StaticText(panel, label="Speed:")
        self.speed_ctrl = wx.SpinCtrl(panel, value=str(self.defaults['speed']), min=1, max=255)
        self.speed_ctrl.SetName("Speed")
        param_sizer.Add(speed_label, flag=wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_RIGHT)
        param_sizer.Add(self.speed_ctrl, flag=wx.EXPAND)

        # Pitch (0-255, default 64)
        pitch_label = wx.StaticText(panel, label="Pitch:")
        self.pitch_ctrl = wx.SpinCtrl(panel, value=str(self.defaults['pitch']), min=0, max=255)
        self.pitch_ctrl.SetName("Pitch")
        param_sizer.Add(pitch_label, flag=wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_RIGHT)
        param_sizer.Add(self.pitch_ctrl, flag=wx.EXPAND)

        # Mouth (0-255, default 128)
        mouth_label = wx.StaticText(panel, label="Mouth:")
        self.mouth_ctrl = wx.SpinCtrl(panel, value=str(self.defaults['mouth']), min=0, max=255)
        self.mouth_ctrl.SetName("Mouth")
        param_sizer.Add(mouth_label, flag=wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_RIGHT)
        param_sizer.Add(self.mouth_ctrl, flag=wx.EXPAND)

        # Throat (0-255, default 128)
        throat_label = wx.StaticText(panel, label="Throat:")
        self.throat_ctrl = wx.SpinCtrl(panel, value=str(self.defaults['throat']), min=0, max=255)
        self.throat_ctrl.SetName("Throat")
        param_sizer.Add(throat_label, flag=wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_RIGHT)
        param_sizer.Add(self.throat_ctrl, flag=wx.EXPAND)

        # Inflection (0-100, default 50)
        inflection_label = wx.StaticText(panel, label="Inflection:")
        self.inflection_ctrl = wx.SpinCtrl(panel, value=str(self.defaults['inflection']), min=0, max=100)
        self.inflection_ctrl.SetName("Inflection")
        param_sizer.Add(inflection_label, flag=wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_RIGHT)
        param_sizer.Add(self.inflection_ctrl, flag=wx.EXPAND)

        main_sizer.Add(param_sizer, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=10)

        # Buttons
        button_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.preview_btn = wx.Button(panel, label="Preview")
        self.preview_btn.Bind(wx.EVT_BUTTON, self.on_preview)
        button_sizer.Add(self.preview_btn, flag=wx.RIGHT, border=10)

        self.render_btn = wx.Button(panel, label="Render to WAV")
        self.render_btn.Bind(wx.EVT_BUTTON, self.on_render)
        button_sizer.Add(self.render_btn)

        main_sizer.Add(button_sizer, flag=wx.ALL | wx.ALIGN_CENTER, border=15)

        panel.SetSizer(main_sizer)

    def get_params(self):
        """Get current parameter values."""
        return {
            'speed': self.speed_ctrl.GetValue(),
            'pitch': self.pitch_ctrl.GetValue(),
            'mouth': self.mouth_ctrl.GetValue(),
            'throat': self.throat_ctrl.GetValue(),
            'inflection': self.inflection_ctrl.GetValue()
        }

    def synthesize(self, text):
        """Synthesize text to WAV data."""
        params = self.get_params()
        wav_data = text_to_wav(
            text,
            pitch=params['pitch'],
            speed=params['speed'],
            mouth=params['mouth'],
            throat=params['throat'],
            inflection=params['inflection']
        )
        return wav_data

    def on_preview(self, event):
        """Preview button handler - synthesize and play audio."""
        text = self.text_ctrl.GetValue().strip()
        if not text:
            wx.MessageBox("Please enter some text to speak.", "No Text", wx.OK | wx.ICON_WARNING)
            return

        # Disable button during playback
        self.preview_btn.Disable()

        def play_audio():
            try:
                wav_data = self.synthesize(text)
                if wav_data:
                    winsound.PlaySound(wav_data, winsound.SND_MEMORY)
                else:
                    wx.CallAfter(wx.MessageBox, "Failed to synthesize audio.", "Error", wx.OK | wx.ICON_ERROR)
            except Exception as e:
                wx.CallAfter(wx.MessageBox, f"Error: {str(e)}", "Error", wx.OK | wx.ICON_ERROR)
            finally:
                wx.CallAfter(self.preview_btn.Enable)

        # Run in thread to keep UI responsive
        thread = threading.Thread(target=play_audio)
        thread.daemon = True
        thread.start()

    def on_render(self, event):
        """Render button handler - save to WAV file."""
        text = self.text_ctrl.GetValue().strip()
        if not text:
            wx.MessageBox("Please enter some text to speak.", "No Text", wx.OK | wx.ICON_WARNING)
            return

        # File save dialog
        with wx.FileDialog(self, "Save WAV file", wildcard="WAV files (*.wav)|*.wav",
                          style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as dlg:
            if dlg.ShowModal() == wx.ID_CANCEL:
                return

            filepath = dlg.GetPath()
            if not filepath.lower().endswith('.wav'):
                filepath += '.wav'

        # Synthesize and save
        try:
            wav_data = self.synthesize(text)
            if wav_data:
                with open(filepath, 'wb') as f:
                    f.write(wav_data)
                wx.MessageBox(f"Saved to {filepath}", "Success", wx.OK | wx.ICON_INFORMATION)
            else:
                wx.MessageBox("Failed to synthesize audio.", "Error", wx.OK | wx.ICON_ERROR)
        except Exception as e:
            wx.MessageBox(f"Error saving file: {str(e)}", "Error", wx.OK | wx.ICON_ERROR)


def main():
    app = wx.App()
    frame = SAMFrame()
    frame.Show()
    app.MainLoop()


if __name__ == '__main__':
    main()
