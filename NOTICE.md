# Notices and attributions

IHAMAICS is built almost entirely from other people's work. This
file records who made what, and under what terms, as accurately as
we can state it.

Nothing here is a claim of ownership over SAM.

## SAM (1982) — SoftVoice, Inc.

The speech engine is a reverse-engineered version of Software
Automatic Mouth, published in 1982 by Don't Ask Software, written
by Mark Barton. The current copyright holder is SoftVoice, Inc.
(www.text2speech.com).

Attempts to contact the company have failed and its website was
last updated in 2009, so the status of the original software is
best described as
[Abandonware](http://en.wikipedia.org/wiki/Abandonware).

**This means no open source licence can be granted over the SAM
engine, or over anything derived from it — including the Python
port in this repository.** The maintainers of this project do not
hold copyright in SAM and do not purport to license it to anyone.
Use it at your own risk.

## The JavaScript port — Christian Schiffler and others

The engine here descends from the vanilla JavaScript port at
[discordier/sam](https://github.com/discordier/sam) by Christian
Schiffler, itself based on the C adaptation by
[Stefan Macke](https://github.com/s-macke/SAM), with refactorings
by [Vidar Hokstad](https://github.com/vidarh/SAM) and
[8BitPimp](https://github.com/8BitPimp/SAM).

The Python engine in `nvda-addon/synthDrivers/sam/` is a direct
port of that JavaScript; each module names the `.es6` file it came
from, and the C engine in `native/` was ported from the Python.
That JavaScript is no longer copied into this repository — it is
upstream, at the link above — but the attribution stands: the code
here is derived from it. The same abandonware constraint applies.

## CMU Pronouncing Dictionary — Carnegie Mellon University

`nvda-addon/synthDrivers/sam/cmudict.txt` is the CMU Pronouncing
Dictionary from [cmusphinx/cmudict](https://github.com/cmusphinx/cmudict),
redistributed under the licence below. The same notice is retained
verbatim in the `;;;` header of `cmudict.txt` itself, and ships
inside the built `.nvda-addon`.

```
Copyright (C) 1993-2015 Carnegie Mellon University. All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions
are met:

1. Redistributions of source code must retain the above copyright
   notice, this list of conditions and the following disclaimer.
   The contents of this file are deemed to be source code.

2. Redistributions in binary form must reproduce the above copyright
   notice, this list of conditions and the following disclaimer in
   the documentation and/or other materials provided with the
   distribution.

This work was supported in part by funding from the Defense Advanced
Research Projects Agency, the Office of Naval Research and the National
Science Foundation of the United States of America, and by member
companies of the Carnegie Mellon Sphinx Speech Consortium. We acknowledge
the contributions of many volunteers to the expansion and improvement of
this dictionary.

THIS SOFTWARE IS PROVIDED BY CARNEGIE MELLON UNIVERSITY ``AS IS'' AND
ANY EXPRESSED OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
PURPOSE ARE DISCLAIMED.  IN NO EVENT SHALL CARNEGIE MELLON UNIVERSITY
NOR ITS EMPLOYEES BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```

## This project's own contribution

What is original here is the Python port of the engine, the NVDA
synthesizer driver, the packaging and the wxPython application.
That work is a derivative of SAM and therefore cannot be offered
under an open source licence either, for the reasons above.
