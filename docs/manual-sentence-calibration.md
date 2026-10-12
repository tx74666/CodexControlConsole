# Manual sentence timing

Use the saved audio and the existing lyric lines. Sentence marking changes timing points; it does not rewrite the words, split sentences into words, or discard older word timing data.

1. Open the song's lyrics and enable sentence marking. The calibration cursor selects the first non-empty lyric line, independently of the old lyric timestamps.
2. Play the song. No separate first-onset tap is needed: a new first sentence starts at audio time zero. An already saved first onset stays unchanged.
3. Press **Insert** when each sentence ends. The point closes that sentence and starts the next non-empty lyric line at the same audio time. It immediately applies to whole-line playback and advances the marking cursor after the local pending journal is written; there is no separate Apply step. Old caption rest rows are skipped during this sequence. Further sentence ends can be marked while an earlier network save is pending; saves drain in order.
4. At the end of the last sentence, press **Insert** once more to close it. During playback, the whole current sentence lights together.

The visible cursor follows audio time. The red point indicators refer to start/end timestamps beside their lyric line; pending points are applied locally but the status does not call them saved before acknowledgement. They are not word positions or a new waveform graph. Pausing and seeking do not choose a different calibration sentence automatically. To correct a point, select the intended sentence and its start/end, edit the timestamp, then apply that correction. Insert always records the sentence end, even with Start selected in the correction editor. A middle sentence without a saved start can use the preceding sentence's saved end; an unmarked gap must be marked in order rather than guessed from old captions. Point removal affects that sentence point, not the lyric text or older word marks.

Do not use repeated keydown, shortcuts with modifiers, or Insert inside a text input to record points. Save errors remain visible and can be retried with the original captured times, without moving the cursor a second time. A local journal failure retains the current target until retry can protect the point. A point awaiting confirmation is not reported as saved. Selecting another song or lyric language ends the current calibration selection so a delayed response cannot modify the new selection.

These controls provide a manual timing workflow. Synthetic playback and persistence tests establish its behavior; they do not prove the singing in an unmarked song is correctly aligned. Listen to the marked boundaries before treating a song as calibrated.
