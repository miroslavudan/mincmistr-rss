# RSS feed pro blog mincmistr.cz

Shoptet neumí generovat RSS feed z blogových článků, tak to za něj dělá
tento projekt. Python skript stáhne výpis článků z
`https://www.mincmistr.cz/blog/`, z každého vytáhne titulek, odkaz, datum
a perex, a uloží je jako validní RSS 2.0 feed (`feed.xml`).

Feed se automaticky obnovuje **každé 2 hodiny** pomocí GitHub Actions
a je publikován zdarma přes GitHub Pages.

**Výsledná URL feedu** (po zprovoznění):
`https://<tvuj-github-username>.github.io/mincmistr-rss/feed.xml`

---

## Co je v balíčku

| Soubor                             | Co dělá                                                     |
|------------------------------------|-------------------------------------------------------------|
| `generate_rss.py`                  | Python skript, který stáhne blog a vygeneruje feed.xml      |
| `requirements.txt`                 | Python závislosti                                           |
| `.github/workflows/update-rss.yml` | Workflow — spouští skript každé 2 h a commituje feed.xml    |
| `index.html`                       | Malá titulní stránka pro GitHub Pages                       |
| `.gitignore`                       | Ignoruje Python cache                                       |
| `README.md`                        | Tento návod                                                 |

---

## Zprovoznění — krok za krokem

Nepředpokládám u tebe žádné zkušenosti s GitHubem. Celé to zabere ~10 minut.

### 1) Založ si GitHub účet (pokud ho nemáš)

Jdi na [github.com](https://github.com/signup) a zaregistruj se.

### 2) Vytvoř nový repozitář

1. Klikni vpravo nahoře na **+** → **New repository**
2. **Repository name:** `mincmistr-rss` (nebo jak chceš)
3. **Visibility:** můžeš nechat *Public* (je to jen RSS feed, nic citlivého)
4. Zaškrtni **Add a README file** (abys mohl klonovat do prázdna)
5. Klikni **Create repository**

### 3) Nahraj tyto soubory do repozitáře

Nejjednodušší varianta (bez git příkazů, přes webové rozhraní):

1. V novém repu klikni na **Add file → Upload files**
2. Přetáhni všechny soubory z mé složky (kromě `README.md`, ten tam už je —
   nebo ho nech přepsat, na tom nezáleží):
   - `generate_rss.py`
   - `requirements.txt`
   - `index.html`
   - `.gitignore`
   - `README.md` (tento)

   **POZOR — důležité:** složku `.github/workflows/` webové rozhraní
   nedovolí přetáhnout přímo. Udělej to takto:
   1. Klikni **Add file → Create new file**
   2. Do pole s názvem napiš: `.github/workflows/update-rss.yml`
      (lomítka automaticky vytvoří podsložky)
   3. Zkopíruj obsah souboru `update-rss.yml` z balíčku
   4. Klikni **Commit changes**

3. Nakonec dole klikni **Commit changes** (u ostatních souborů).

### 4) Zapni GitHub Pages

1. V repu jdi na **Settings** (horní menu repa, ne tvoje osobní)
2. V levém menu **Pages**
3. V sekci **Build and deployment**:
   - **Source:** *Deploy from a branch*
   - **Branch:** `main` / `/ (root)`
   - Klikni **Save**
4. Po ~1 minutě se nahoře objeví zelený box s URL tvého webu, např.:
   `https://tvuj-username.github.io/mincmistr-rss/`

### 5) Spusť workflow poprvé (ručně)

Workflow poběží sám každé 2 hodiny, ale poprvé ho spustíme ručně,
ať máme feed hned:

1. V repu klikni na záložku **Actions**
2. Pokud GitHub zobrazí „Workflows aren't being run on this repository“,
   klikni **I understand my workflows, go ahead and enable them**
3. V levém menu vyber **Update RSS feed**
4. Vpravo klikni **Run workflow** → **Run workflow**
5. Za ~30 sekund by se měl objevit zelený check ✓
6. V repu by se měl objevit nový soubor `feed.xml`

### 6) Ověř feed

Otevři v prohlížeči:

```
https://<tvuj-username>.github.io/mincmistr-rss/feed.xml
```

Měl bys vidět XML s articles. Můžeš ho i ověřit na
[validator.w3.org/feed](https://validator.w3.org/feed/).

Hotovo 🎉 — feed se teď obnovuje každé 2 hodiny automaticky.

---

## Vložení feedu do Shoptetu

Aby RSS čtečky feed automaticky objevily, když někdo navštíví tvůj e-shop:

1. V Shoptet administraci: **Vzhled a obsah → Editor HTML kódu**
2. Do sekce `<head>` přidej:

   ```html
   <link rel="alternate" type="application/rss+xml"
         title="Mincmistr.cz Blog"
         href="https://tvuj-username.github.io/mincmistr-rss/feed.xml" />
   ```

(Nahraď `tvuj-username` tvým GitHub usernamem.)

Také můžeš přidat viditelný odkaz v patičce nebo u blogu:

```html
<a href="https://tvuj-username.github.io/mincmistr-rss/feed.xml">
  📡 Odebírat blog (RSS)
</a>
```

---

## Změna frekvence aktualizace

Uprav v souboru `.github/workflows/update-rss.yml` řádek:

```yaml
- cron: '0 */2 * * *'
```

- `'0 * * * *'` — každou hodinu
- `'0 */6 * * *'` — každých 6 hodin
- `'0 4 * * *'` — každý den ve 4:00 UTC (6:00 CEST v létě)

Cron v GitHub Actions používá UTC. Změnu stačí commitnout, projeví se hned.

---

## Lokální testování

Pokud chceš skript spustit ručně na svém počítači:

```bash
pip install -r requirements.txt
python3 generate_rss.py
```

Výstup: `feed.xml` v aktuální složce.

Volby:
- `--output /cesta/k/feed.xml` — jiná cesta
- `--limit 30` — počet článků
- `--no-detail` — rychlejší, ale méně přesné
- `--verbose` — podrobný výpis

---

## Pokud něco selže

**Workflow ve Actions skončí červeně 🔴**
- Klikni na neúspěšný běh → rozbal log → koukni se na chybu
- Nejčastější příčina: Shoptet změnil šablonu blogu, takže selektory
  v `generate_rss.py` (v sekci `CONFIG`) nesedí. Otevři blog
  v prohlížeči, přes DevTools najdi třídy karet článků a přidej je
  na začátek `ARTICLE_CARD_SELECTORS` / `TITLE_SELECTORS` atd.

**Feed je prázdný nebo jen s pár články**
- Stejný důvod — parser nenašel všechny karty. Viz výše.

**GitHub Pages URL nefunguje**
- Zkontroluj **Settings → Pages**, že Source je `main` / `/ (root)`
- Po první změně může trvat až 10 minut, než se to projeví

**Dotaz / potíže**
- Pošli mi chybovou hlášku z Actions nebo ukázku HTML ze stránky blogu,
  upravím skript.

---

## Závislosti

- Python 3.8+
- `requests`
- `beautifulsoup4`
- `lxml`
