# Ibahu: Breaking Away from the Klatt Sound

## The Problem

Most speech synthesizers since the 1980s are Klatt derivatives:
- eSpeak (Klatt-based)
- rsynth (Klatt-based)
- DECtalk (Klatt-based)
- Festival/Flite (often Klatt)
- SAM (simpler formant, same DNA)

They all share:
- LF or Rosenberg glottal pulse source
- 5-6 cascade biquad resonators
- Rule-based formant transitions
- Noise + parallel filters for fricatives

**Result**: They all sound like variations of the same voice. "That synth speech sound."

## Options for Differentiation

### Option A: Waveguide-First Architecture

Make physical modeling the **primary** engine, not an afterthought.

**How it works**:
- Model vocal tract as a series of cylindrical tube sections
- Sound propagates through waveguide (Kelly-Lochbaum algorithm)
- Formants emerge naturally from tube geometry
- Coarticulation happens automatically from physics

**Advantages**:
- Sounds fundamentally different from Klatt
- Natural transitions between sounds
- Consonants emerge from constrictions (not bolted-on noise)
- Physically meaningful parameters (tongue position, lip aperture)
- Largely unexplored for practical speech synths

**Trade-offs**:
- Less direct control over exact formant frequencies
- Must convert formant targets to area functions
- Slightly more computation (but trivial on modern hardware)

**Consonant handling**:
- Fricatives: Narrow constriction + turbulence injection
- Plosives: Complete closure then release
- Nasals: Couple nasal tract branch
- All emerge from the same physical model

---

### Option B: Additive Synthesis Primary

Generate harmonics directly, shape with formant envelopes.

**How it works**:
```
output = Σ(sin(n * f0 * t) * A[n] * formant_envelope(n * f0))
```
- Each harmonic generated independently
- Amplitude shaped by formant curve
- Very precise control over spectrum

**Advantages**:
- Crystalline, precise sound
- Individual harmonic control (unique capability)
- Can do harmonic stretching, inharmonicity
- No filter artifacts
- Very "clean" machine aesthetic

**Trade-offs**:
- Higher computation (many oscillators)
- Consonants are difficult (noise doesn't fit the model well)
- Transitions require interpolating many parameters

**Consonant handling**:
- Fricatives: Requires separate noise path (hybrid)
- Plosives: Challenging, need transient model
- Less natural integration than waveguide

---

### Option C: Novel Source Model (Keep Filters)

Replace the glottal source while keeping formant filters.

**Options**:
- **FM-based source**: Operator stack creates rich harmonics
- **Waveshaping source**: Simple wave → complex spectrum
- **Physical fold model**: Mass-spring vocal fold simulation
- **Wavetable source**: Morphable glottal shapes

**Advantages**:
- Different character even with standard filters
- Can create sounds LF model cannot
- More "synthesizer" aesthetic
- Easier to implement than full waveguide

**Trade-offs**:
- Still using Klatt filters (still sounds somewhat similar)
- Source alone may not be enough differentiation

---

### Option D: Different Filter Topology

Keep source-filter model but change the filters.

**Options**:
- **Parallel-only**: All formants in parallel (brighter, buzzier)
- **Higher-order filters**: 8th+ order (sharper peaks)
- **Comb + resonators**: Different resonance character
- **Allpass networks**: Phase-based timbre changes
- **Modal synthesis**: Resonant modes instead of formants

**Advantages**:
- Can achieve sounds cascade filters cannot
- May find unexplored timbral territory

**Trade-offs**:
- Still fundamentally source-filter
- May not be different enough

---

### Option E: Embrace Digital Character

Lean into machine aesthetics as a feature.

**Elements**:
- **Quantized formants**: Snap to frequency grid
- **Bit-crushed harmonics**: Deliberate resolution reduction
- **Ring modulation**: As core timbre element
- **Aliasing as character**: Like classic chip synths
- **Granular voice**: Micro-segments (though approaches sampling)

**Advantages**:
- Unique aesthetic space
- Embraces being a machine
- Appeals to electronic music / retrocomputing crowd

**Trade-offs**:
- May limit "pleasant" end of voice range
- Niche appeal

---

## Recommendation: Waveguide-First

For Ibahu, **waveguide-first** offers the best path to a distinctive sound:

1. **Fundamentally different** from all Klatt synths
2. **Consonants integrate naturally** - no separate noise system
3. **Physically meaningful parameters** - intuitive for users
4. **Natural coarticulation** - sounds flow better
5. **Unexplored territory** - not yet done in practical synths
6. **Scales well** - can add detail by adding tube sections

### Waveguide Architecture for Ibahu

```
┌─────────────────────────────────────────────────────────────────┐
│                      GLOTTAL SOURCE                              │
│  ┌─────────────┐                                                │
│  │ Vocal Fold  │  Physical or parametric model                  │
│  │ Oscillator  │  → generates pressure wave                     │
│  └─────────────┘                                                │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    VOCAL TRACT WAVEGUIDE                         │
│                                                                  │
│  Glottis → [T1] → [T2] → [T3] → ... → [TN] → Lips → Output     │
│              │      │      │            │                        │
│           Area   Area   Area         Area                        │
│           A[1]   A[2]   A[3]         A[N]                        │
│                                                                  │
│  Each junction: reflection/transmission based on area ratio      │
│  Formants emerge from tube geometry                              │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ NASAL BRANCH (coupled at velum)                          │   │
│  │ [N1] → [N2] → [N3] → Nostril                            │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  TURBULENCE INJECTION (for fricatives):                         │
│  Noise injected at constriction points                          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      RADIATION                                   │
│  Lip radiation filter (highpass characteristic)                  │
└─────────────────────────────────────────────────────────────────┘
```

### Parameter Mapping

Instead of direct formant control, users control:

| Parameter | Range | Maps To |
|-----------|-------|---------|
| `tongue_position` | 0.0-1.0 | Constriction location along tract |
| `tongue_height` | 0.0-1.0 | Constriction degree (area) |
| `lip_rounding` | 0.0-1.0 | Final tube section area |
| `lip_protrusion` | 0.0-1.0 | Tract length extension |
| `jaw_opening` | 0.0-1.0 | Overall tract aperture |
| `velum` | 0.0-1.0 | Nasal coupling (0=closed, 1=open) |
| `larynx_height` | 0.0-1.0 | Tract length at glottis end |
| `constriction_loc` | 0.0-1.0 | Fricative turbulence location |
| `constriction_area` | 0.0-1.0 | Fricative turbulence intensity |

### IPA to Area Function

Each IPA phoneme maps to a target area function:

```cpp
struct AreaFunction {
    std::array<float, 16> areas;  // Cross-sectional areas
    float nasal_coupling;          // Velum opening
    float turbulence_location;     // For fricatives
    float turbulence_intensity;    // Noise injection amount
};

// Example: /i/ (high front vowel)
AreaFunction vowel_i = {
    .areas = {1.0, 0.8, 0.4, 0.2, 0.3, 0.5, 0.8, 1.2,
              1.5, 1.8, 2.0, 2.2, 2.4, 2.6, 2.8, 3.0},
    .nasal_coupling = 0.0,
    .turbulence_location = 0.0,
    .turbulence_intensity = 0.0
};

// Example: /s/ (alveolar fricative)
AreaFunction fricative_s = {
    .areas = {1.0, 1.0, 1.0, 0.8, 0.3, 0.05, 0.3, 0.8,
              1.2, 1.5, 1.8, 2.0, 2.2, 2.4, 2.6, 2.8},
    .nasal_coupling = 0.0,
    .turbulence_location = 0.35,  // At constriction
    .turbulence_intensity = 0.8
};
```

### Keeping Direct Control Available

For users who want formant-level control:
- **Formant-to-area converter**: Takes F1-F5 targets, solves for area function
- **Hybrid parameter set**: Can specify either areas OR formants
- Allows familiar control while using waveguide synthesis

---

## Implementation Priority

1. **Phase 1**: Basic waveguide with fixed tube (sustained vowels)
2. **Phase 2**: Area function interpolation (vowel transitions)
3. **Phase 3**: Turbulence injection (fricatives)
4. **Phase 4**: Nasal coupling (nasals)
5. **Phase 5**: Plosive closures and releases
6. **Phase 6**: IPA-to-area mapping database
7. **Phase 7**: Formant-to-area converter (optional direct control)

This approach gives Ibahu a fundamentally different sound while still achieving intelligible speech synthesis.
