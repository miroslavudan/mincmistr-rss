# Vlastní styly pro Mincmistr.cz

Jediný soubor `mincmistr.css` s našimi úpravami vzhledu e-shopu
[mincmistr.cz](https://www.mincmistr.cz/). Načítá se v záhlaví e-shopu
(Shoptet → Vzhled a obsah → Editor → HTML kódy → Záhlaví) **za** šablonou,
takže ji přebíjí.

**Proč je to tady a ne na Shoptetu:** do souborového prostoru Shoptetu se nahrává
ručně přes FTP. Odsud se změna nasadí `git push`em, má historii a jde vrátit.
Až se vzhled ustálí, soubor se překlopí na Shoptet a odkaz se přepne.

## Jak se to nasazuje

1. Uprav `mincmistr.css`, commitni, `git push`.
2. Za chvíli je změna na `https://miroslavudan.github.io/mincmistr-sablona/mincmistr.css`.
3. Když se má projevit i lidem s uloženou kopií, zvyš `?v=` v odkazu v záhlaví.

## Pravidla

- Každý blok má v komentáři **číslo úkolu v ClickUpu**, ke kterému patří.
- Komentáře a názvy anglicky (technický artefakt), zbytek dokumentace česky.
- Změny se zapisují do `docs/changelog.md` ve složce Mincmistr.
