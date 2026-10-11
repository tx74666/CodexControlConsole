# Manual sentence timing

Use the saved audio and the existing lyric lines. Sentence marking changes timing points; it does not rewrite the words, split sentences into words, or discard older word timing data.

1. Open the song's lyrics and enable sentence marking. The calibration cursor selects the first non-empty lyric line, independently of the old lyric timestamps.
2. Play the song. Press **Insert** when the first sentence starts. This records the audio player's current time as that sentence's start.
3. Press **Insert** at each change to the next sentence. One point closes the current sentence and starts the next non-empty lyric line at the same time. Old caption rest rows are skipped during this sequence.
4. At the end of the last sentence, press **Insert** once more to close it. During playback, the whole current sentence lights together.

The visible cursor follows audio time. The red point indicators refer to saved start/end timestamps beside their lyric line; they are not word positions or a new waveform graph. Pausing and seeking do not choose a different calibration sentence automatically. To correct a point, select the intended sentence and its start/end, edit the timestamp, then save. Point removal affects that sentence point, not the lyric text or older word marks.

Do not use repeated keydown, shortcuts with modifiers, or Insert inside a text input to record points. Save errors remain visible and can be retried; a point awaiting confirmation is not reported as saved. Selecting another song or lyric language ends the current calibration selection so a delayed response cannot modify the new selection.

These controls provide a manual timing workflow. Synthetic playback and persistence tests establish its behavior; they do not prove the singing in an unmarked song is correctly aligned. Listen to the marked boundaries before treating a song as calibrated.
