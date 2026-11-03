# Landing page fonts

Self-hosted, so the page makes no request to a font host, and subset to Latin (the Basic Latin and Latin-1
blocks, general punctuation, the euro and trademark signs, the minus sign, four arrows and the two
comparison signs), so that no Greek or Cyrillic glyph ships to a page that never uses one.

| File | Family | Use | Licence |
| --- | --- | --- | --- |
| Newsreader-Latin.woff2 | Newsreader, variable weight 400 to 600, optical size fixed at 48 | headlines and large numbers | SIL OFL 1.1, NEWSREADER-OFL.txt |
| Geist-Latin.woff2 | Geist, variable weight 100 to 900 | body and interface | SIL OFL 1.1, ../../../ui/fonts/GEIST-OFL.txt |
| GeistMono-Latin.woff2 | Geist Mono, variable weight 100 to 900 | commits and code | SIL OFL 1.1, ../../../ui/fonts/GEIST-OFL.txt |

Neither licence declares a Reserved Font Name, so a subset keeps its family's name.

- Newsreader, (c) 2020 The Newsreader Project Authors (Production Type), from
  https://github.com/google/fonts/tree/main/ofl/newsreader (`Newsreader[opsz,wght].ttf`, taken 2026-11-02).
- Geist and Geist Mono, (c) 2023 Vercel in collaboration with basement.studio: the variable files in
  `ui/fonts/` (see the README there), subset here.

Made with fontTools (not a dependency of this project; run once, the output is committed):

```bash
UNI="U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,U+0329,U+2000-206F,U+2074,U+20AC,U+2122,U+2190-2193,U+2212,U+2215,U+2264-2265,U+FEFF,U+FFFD"
uvx --from "fonttools[woff]" fonttools varLib.instancer "Newsreader[opsz,wght].ttf" wght=400:600 opsz=48:48 -o nr.ttf
uvx --from "fonttools[woff]" pyftsubset nr.ttf --unicodes="$UNI" --layout-features='kern,liga,calt,ccmp,locl,mark,mkmk,tnum,lnum,case' --flavor=woff2 --output-file=Newsreader-Latin.woff2
uvx --from "fonttools[woff]" pyftsubset ui/fonts/Geist-Variable.woff2 --unicodes="$UNI" --layout-features='kern,liga,calt,ccmp,locl,mark,mkmk,tnum,lnum,case,zero' --flavor=woff2 --output-file=Geist-Latin.woff2
uvx --from "fonttools[woff]" pyftsubset ui/fonts/GeistMono-Variable.woff2 --unicodes="$UNI" --layout-features='kern,liga,calt,ccmp,locl,mark,mkmk,tnum,lnum,case,zero' --flavor=woff2 --output-file=GeistMono-Latin.woff2
```
