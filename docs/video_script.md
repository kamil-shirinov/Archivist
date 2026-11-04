# The demo video: script

The three-minute demo video, as voiced and captioned: 2:54 in all, eight scenes. At least 80% of it is screen recordings of the working product; the rest is the logo at the start and the close. The voice is English text-to-speech made offline with Kokoro (af_heart; a second cut uses bm_george on the same timings), and the captions follow it word for word.

## 1. 0:00–0:16

**Screen.** The logo reveal, then the landing page's hero and the story behind it. From the first second, a line at the top says: Before the hackathon: one idea, from my bank internship · Built during the hackathon, 26 Oct – 4 Nov 2026.

**Voice.** Before this hackathon I had one idea, from my bank internship. Everything you'll see, I built during it. At the bank I wrote a parser for two thousand old memos, then found there was nothing to run it on: no archive, and the oldest records only on paper.

## 2. 0:16–0:31

**Screen.** A 1939 Treasury Bulletin page in the review app with its pen loops; pointing at a value in the record draws the line to its cell on the scan.

**Voice.** Archivist turns scanned financial records into a database you can check. Every value is cited to its spot on the page, read twice, checked by arithmetic, and sent to a person when in doubt.

## 3. 0:31–1:13

**Screen.** A live read in the local app (`python -m archivist.live`) of a development Treasury page, September 1939, page 24: Muse Glimmer on Modal sorts it, Muse Spark 1.3 reads it, SAM 3.1 looks for covered ink, Muse Spark 1.3 re-reads every cell blind, and every call is listed as it happens with its time and cost. The read took 310.8 s and is shown sped up, with the true factor on screen; then its summary (51 accepted, 51 sent to a person, $0.1312) and the page it produced.

**Voice.** This is a live run. Muse Glimmer, running on Modal, works out which table the page holds. Muse Spark 1.3 reads every value and marks where it saw it. SAM 3.1 checks for stamps or stains over the ink. Then each cell is read again, blind, from a crop alone, so the second read can't copy the first. Plain code checks the arithmetic: totals, running balances, dates. On this page from 1939, half the values go to a person: Archivist accepts only what it can check. Every call, with its time and cost, is listed as it happens.

## 4. 1:13–1:32

**Screen.** The review queue on a synthetic ledger card: the sheet number, read as 35 and then as 3, ringed on the scan, with the cut-out cell and both reads; the key 1 records the answer.

**Voice.** Here's what it's for. On this ledger card the two reads disagree: thirty-five, then three. Archivist doesn't guess, and it never changes a value. It sends the cell to a person, with the crop and both readings, and records their decision.

## 5. 1:32–1:59

**Screen.** The landing page's 12× headline, the ledger of pre-registered targets with one row opened, then the "Planned before the data" timeline.

**Voice.** On a pre-registered test of 4,267 values, Archivist let through twelve times fewer wrong values than Muse Spark reading alone: 0.36 percent against 4.45. It caught 94 percent of the mistakes, and sent about one value in five to a person. Every test was committed before it ran.

## 6. 1:59–2:18

**Screen.** The landing page's "Run on" switch flipping to Your own hardware; a Replay, in the local app, of a recorded open-weights read of a synthetic card (Muse Spark Open on Baseten, labelled Replay on screen, since every page the app accepts already has cached open-weights answers); a live Muse Glimmer call on Modal from a second live read (October 1939, page 24), the step panel naming it; the open-weights figure, 0.30%.

**Voice.** Banks often can't send documents out. Flip one switch, and both reads run on Meta's open weights: here, a recorded run of Muse Spark Open on Baseten, with Muse Glimmer on Modal sorting the pages. Accuracy holds: 0.30 percent.

## 7. 2:18–2:46

**Screen.** The landing page's real-scans section: the intervals under the official key and the corrected key, then the corrected key's table above the official result.

**Voice.** On over fifty years of real US Treasury scans, the reading held up. Most errors came from old templates meeting redesigned pages, and from a slip in my own answer key, which I fixed by a rule written down first. With that fix, Archivist accepted no wrong values on pages that match their template. Counting redesigned pages too, sixteen percent. All of it is published.

## 8. 2:46–2:54

**Screen.** The GitHub repository, then the close: the mark, "The archive that shows its work.", the repository and the live demo addresses.

**Voice.** Archivist: the archive that shows its work. Open source, and every number reproducible.

## Where each spoken number comes from

| Spoken | Source |
|---|---|
| two thousand old memos | README.md, The problem (about 2,000 legacy memos) |
| half the values go to a person (51 of 102) | the live read's own record, shown on screen (51 accepted, 51 sent to a person) |
| thirty-five, then three | data/bundles/test-archivist-A/bundle.json, field L:card-04-1:hdr:sheet_no (read 35, re-read 3) |
| 4,267 values; twelve times fewer; 0.36 against 4.45 percent | results/test_report.json: H1, 12 wrong of 3,330 accepted (0.36%) against 189 of 4,251 for one read (4.45%), 12.3 times |
| 94 percent of the mistakes | results/test_report.json: H2, 177 of 189 caught (93.65%) |
| about one value in five | results/test_report.json: H3, 921 of 4,267 sent to a person (21.58%) |
| 0.30 percent | results/test_report.json: H4, 10 wrong of 3,296 accepted on open weights (0.30%) |
| over fifty years of Treasury scans | data/real/split.json: held-out issues from January 1940 to June 1994 |
| no wrong values on pages that match their template | results/real_test/held_out/score_corrected/score.md: left out, as run, corrected key, 0.0% (0.0%–0.0%) |
| sixteen percent | results/real_test/held_out/score_corrected/score.md: kept, as run, corrected key, 16.3% (6.1%–33.3%) |

The two live reads (scenes 3 and 6) called the models for real, on public-domain development pages; every call went through archivist.models, within the spend caps, and is in results/spend_ledger.jsonl: 160 paid calls, $0.256 in all. The second read's page had been read before by the template's arithmetic test, so half of its calls were answered from the cache; only its Muse Glimmer call is shown.
