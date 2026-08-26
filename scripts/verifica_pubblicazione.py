#!/usr/bin/env python
"""Controllo obbligatorio pre-pubblicazione per PrimaVoce.

Verifica meccanicamente le regole della skill primavoce-redazione che in
passato sono state saltate da Luna quando lavorava con un budget di
iterazioni troppo basso o con un modello locale poco affidabile:

  1. Ogni pagina in curiosita/*.html e articoli/*.html ha almeno un <img>.
  2. Ogni pagina in curiosita/*.html e articoli/*.html è raggiungibile da un
     link in index.html (nessuna pagina "orfana").
  3. Nessuna pagina pubblica contiene una riga "Fonti:", "Fonte:",
     "Bibliografia", "Sitografia" o equivalenti (regola inderogabile n.9).
  4. Ogni pagina in curiosita/*.html e articoli/*.html ha esattamente un <h1>.
  5. Il corpo dell'articolo ha almeno ~500 parole di testo visibile
     (soglia leggermente sotto le 600 richieste, per tollerare markup diverso
     senza falsi negativi troppo aggressivi — è comunque un campanello
     d'allarme, non solo un'estetica).
  6. Nessun href verso curiosita/ presente nella versione committata
     precedente (HEAD) è scomparso dalla homepage attuale.
  7. Ogni immagine referenziata da <img src="..."> esiste, e il suo
     contenuto binario reale (magic bytes) corrisponde all'estensione del
     file — scoperto il 26/08/2026: un file salvato come .webp che in
     realtà era un JPEG, servito da GitHub Pages come image/webp e quindi
     visualizzato rotto da ogni browser.
  8. Nessuna immagine referenziata supera 1.5 MB (il sito deve restare
     leggero; un'immagine più pesante va compressa prima del commit).
  9. Nessuna didascalia/credito fotografico contiene segnaposto come
     "Sconosciuto", "Unknown", "N/A", "TODO" — se l'autore/licenza non è
     stato verificato con l'API di Wikimedia come richiede la skill, il
     credito non va inventato: la pagina deve essere corretta prima del
     commit, non pubblicata con un'attribuzione fittizia.
  10. Tutte le classi CSS usate (class="...") nella pagina esistono
      davvero in uno dei fogli di stile locali collegati (<link
      rel="stylesheet" href="...">) — scoperto il 26/08/2026: un articolo
      pubblicato con classi come "article-hero", "highlight", "location"
      mai definite in article.css, quindi renderizzate senza alcuno stile.
  11. Nessun pattern HTML palesemente rotto (tag di chiusura duplicato
      tipo "</</li>", backslash prima di una virgoletta di attributo tipo
      rel="stylesheet\").

Uscita 0 = tutto ok, si può proseguire con git commit.
Uscita 1 = almeno un controllo fallito, elenco degli errori su stdout.
NON esegue il commit. Va lanciato da terminale prima di 'git commit', o
tramite git hook pre-commit (già installato in .git/hooks/pre-commit).

Modalità:
  python verifica_pubblicazione.py            → controlla SOLO le pagine
                                                  aggiunte o modificate nello
                                                  staging area corrente
                                                  (git diff --cached). Questa
                                                  è la modalità usata dal git
                                                  hook: non blocca un commit
                                                  per articoli vecchi che
                                                  nessuno sta toccando.
  python verifica_pubblicazione.py --tutto     → controlla OGNI pagina del
                                                  sito, anche quelle non
                                                  toccate in questo commit.
                                                  Utile per un audit
                                                  periodico dell'arretrato,
                                                  non per bloccare un commit.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FONTI_PATTERN = re.compile(
    r'>\s*(Fonti?|Fonte consultata|Bibliografia|Sitografia)\s*:',
    re.IGNORECASE,
)
CREDITO_FASULLO_PATTERN = re.compile(
    r'\b(Sconosciut[oa]|Unknown|N/?A|TODO|autore non trovato)\b',
    re.IGNORECASE,
)
DIMENSIONE_MASSIMA_IMMAGINE = 1_500_000  # ~1.5 MB


def formato_reale_immagine(dati: bytes) -> str | None:
    """Riconosce il formato reale di un file immagine dai suoi magic bytes,
    indipendentemente dall'estensione con cui è stato salvato."""
    if dati[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if dati[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if dati[:4] == b"RIFF" and dati[8:12] == b"WEBP":
        return "webp"
    if dati[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if dati[:2] == b"BM":
        return "bmp"
    return None


ESTENSIONE_ATTESA = {"jpeg": {"jpg", "jpeg"}, "png": {"png"}, "webp": {"webp"}, "gif": {"gif"}, "bmp": {"bmp"}}


def controlla_immagini(path: Path, html: str, errori: list[str]) -> None:
    rel = path.relative_to(REPO).as_posix()
    for src in re.findall(r'<img[^>]+src="([^"]+)"', html):
        if src.startswith(("http://", "https://", "data:")):
            continue  # immagine remota, non un file locale da controllare qui
        img_path = (path.parent / src).resolve()
        try:
            img_path.relative_to(REPO.resolve())
        except ValueError:
            errori.append(f"[{rel}] l'immagine '{src}' punta fuori dal repository.")
            continue
        if not img_path.is_file():
            errori.append(f"[{rel}] l'immagine referenziata '{src}' non esiste sul disco.")
            continue

        dati = img_path.read_bytes()
        formato = formato_reale_immagine(dati)
        estensione = img_path.suffix.lstrip(".").lower()
        if formato is None:
            errori.append(f"[{rel}] il file '{src}' non è un formato immagine riconoscibile (magic bytes non validi) — potrebbe essere un errore di download salvato per sbaglio come immagine.")
        elif estensione not in ESTENSIONE_ATTESA.get(formato, set()):
            errori.append(f"[{rel}] il file '{src}' ha estensione .{estensione} ma il contenuto reale è {formato} — il browser lo mostrerà rotto. Rinomina/ricodifica il file con l'estensione giusta.")

        if len(dati) > DIMENSIONE_MASSIMA_IMMAGINE:
            mb = len(dati) / 1_000_000
            errori.append(f"[{rel}] l'immagine '{src}' pesa {mb:.1f} MB, oltre il limite di {DIMENSIONE_MASSIMA_IMMAGINE/1_000_000:.1f} MB — comprimila prima del commit.")


def controlla_credito_fasullo(path: Path, html: str, errori: list[str]) -> None:
    rel = path.relative_to(REPO).as_posix()
    for blocco in re.findall(r'(figcaption|image-caption|image-credit)[^>]*>([^<]{0,200})<', html, re.IGNORECASE):
        testo = blocco[1]
        if CREDITO_FASULLO_PATTERN.search(testo):
            errori.append(f"[{rel}] credito fotografico segnaposto/non verificato trovato: \"{testo.strip()}\" — verifica autore e licenza con l'API di Wikimedia prima di pubblicare, non inventare il credito.")


def classi_definite_nei_css(path: Path, html: str) -> set[str] | None:
    """Legge i fogli di stile locali collegati dalla pagina e restituisce
    l'insieme delle classi CSS che definiscono. None se non trova nessun
    <link rel=\"stylesheet\"> locale (per non generare falsi positivi)."""
    href_css = re.findall(r'<link[^>]+rel="stylesheet"[^>]+href="([^"]+)"', html, re.IGNORECASE)
    classi: set[str] = set()
    trovato_almeno_uno = False
    for href in href_css:
        if href.startswith(("http://", "https://")):
            continue
        css_path = (path.parent / href).resolve()
        if not css_path.is_file():
            continue
        trovato_almeno_uno = True
        testo_css = css_path.read_text(encoding="utf-8", errors="replace")
        classi.update(re.findall(r'\.([a-zA-Z_-][\w-]*)', testo_css))
    return classi if trovato_almeno_uno else None


def controlla_classi_css(path: Path, html: str, errori: list[str]) -> None:
    rel = path.relative_to(REPO).as_posix()
    classi_valide = classi_definite_nei_css(path, html)
    if classi_valide is None:
        return  # nessun CSS locale trovato, non blocchiamo per questo
    usate: set[str] = set()
    for valore in re.findall(r'class="([^"]+)"', html):
        usate.update(valore.split())
    mancanti = sorted(usate - classi_valide)
    if mancanti:
        elenco = ", ".join(mancanti[:8]) + (", ..." if len(mancanti) > 8 else "")
        errori.append(f"[{rel}] classi CSS usate ma mai definite nei fogli di stile collegati: {elenco} — la pagina non avrà lo stile del resto del sito. Riusa le classi di una pagina simile già esistente invece di inventarne di nuove.")


def controlla_html_rotto(path: Path, html: str, errori: list[str]) -> None:
    rel = path.relative_to(REPO).as_posix()
    if re.search(r"</\s*</", html):
        errori.append(f"[{rel}] trovato un tag di chiusura duplicato/rotto tipo '</</...' — HTML malformato.")
    if re.search(r'="[^"<>]*\\+"', html):
        errori.append(f"[{rel}] trovata una virgoletta di attributo preceduta da backslash (es. rel=\"stylesheet\\\") — HTML malformato.")


def pagine_pubbliche() -> list[Path]:
    pagine = []
    for cartella in ("curiosita", "articoli"):
        d = REPO / cartella
        if d.is_dir():
            pagine.extend(sorted(d.glob("*.html")))
    return pagine


def pagine_toccate_in_questo_commit() -> list[Path]:
    """File in curiosita/ o articoli/ aggiunti o modificati nello staging
    area (git add già fatto, prima del commit). Se lo staging è vuoto
    (es. lo script viene lanciato a mano prima di 'git add'), ripiega sui
    file modificati rispetto a HEAD nel working tree."""
    def git_diff(args: list[str]) -> list[str]:
        try:
            out = subprocess.run(
                ["git", "-C", str(REPO)] + args,
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=10, check=True,
            ).stdout
        except Exception:
            return []
        return [l for l in out.splitlines() if l.strip()]

    file_relativi = git_diff(["diff", "--cached", "--name-only", "--diff-filter=ACM"])
    if not file_relativi:
        file_relativi = git_diff(["diff", "--name-only", "--diff-filter=ACM"])

    pagine = []
    for rel in file_relativi:
        if rel.endswith(".html") and (rel.startswith("curiosita/") or rel.startswith("articoli/")):
            p = REPO / rel
            if p.is_file():
                pagine.append(p)
    return pagine


def leggi(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def controlla_pagina(path: Path, index_html: str, errori: list[str]) -> None:
    html = leggi(path)
    rel = path.relative_to(REPO).as_posix()

    if "<img" not in html:
        errori.append(f"[{rel}] nessuna immagine (<img>) trovata — regola: ogni articolo deve avere una foto.")

    h1_count = len(re.findall(r"<h1\b", html, re.IGNORECASE))
    if h1_count != 1:
        errori.append(f"[{rel}] trovati {h1_count} tag <h1> (deve essere esattamente 1).")

    if FONTI_PATTERN.search(html):
        errori.append(f"[{rel}] contiene una riga 'Fonti:'/'Bibliografia'/'Sitografia' vietata nelle pagine pubbliche (regola 9).")

    body_match = re.search(r'<div class="(?:article-body|fact-content)">(.*?)</div>', html, re.S)
    if body_match:
        testo = re.sub(r"<[^>]+>", " ", body_match.group(1))
        parole = [w for w in testo.split() if w.strip()]
        if len(parole) < 500:
            errori.append(f"[{rel}] corpo articolo troppo corto: {len(parole)} parole (soglia ~500-600).")
    else:
        errori.append(f"[{rel}] non trovo un blocco 'article-body' o 'fact-content' da controllare per la lunghezza.")

    if rel.startswith("curiosita/") and path.name not in index_html:
        errori.append(f"[{rel}] non è collegata da nessun link in index.html — pagina orfana, nessuno la troverà sul sito.")

    controlla_immagini(path, html, errori)
    controlla_credito_fasullo(path, html, errori)
    controlla_classi_css(path, html, errori)
    controlla_html_rotto(path, html, errori)


def controlla_schede_non_sparite(errori: list[str]) -> None:
    try:
        prev = subprocess.run(
            ["git", "-C", str(REPO), "show", "HEAD:index.html"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=10, check=True,
        ).stdout
    except Exception:
        return  # niente commit precedente da confrontare, ok
    attuale = leggi(REPO / "index.html")
    prima = set(re.findall(r'href="(curiosita/[^"]+)"', prev))
    dopo = set(re.findall(r'href="(curiosita/[^"]+)"', attuale))
    spariti = prima - dopo
    for href in sorted(spariti):
        errori.append(f"[index.html] la card verso '{href}' era presente nell'ultimo commit e ora è sparita dalla homepage. Se non è una rimozione richiesta esplicitamente da Giuseppe, ripristinala.")


def main() -> int:
    index_path = REPO / "index.html"
    if not index_path.is_file():
        print("Non trovo index.html nella repo:", REPO)
        return 1
    index_html = leggi(index_path)

    modalita_completa = "--tutto" in sys.argv
    pagine = pagine_pubbliche() if modalita_completa else pagine_toccate_in_questo_commit()

    errori: list[str] = []
    for pagina in pagine:
        controlla_pagina(pagina, index_html, errori)
    # Il controllo sulle schede sparite riguarda sempre index.html nel suo
    # complesso, non ha senso limitarlo alle pagine toccate.
    controlla_schede_non_sparite(errori)

    if errori:
        etichetta = "SUL SITO INTERO" if modalita_completa else "SUI FILE DI QUESTO COMMIT"
        print(f"VERIFICA FALLITA {etichetta} — {len(errori)} problema/i trovato/i:\n")
        for e in errori:
            print(" -", e)
        if not modalita_completa:
            print("\n(Questo controllo riguarda solo i file aggiunti/modificati ora. Per un controllo di tutto il sito: python verifica_pubblicazione.py --tutto)")
        return 1

    if not modalita_completa and not pagine:
        print("Verifica OK — nessuna pagina curiosita/ o articoli/ toccata in questo commit, niente da controllare.")
    else:
        print(f"Verifica OK — {len(pagine)} pagina/e controllata/e, nessun problema trovato.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
