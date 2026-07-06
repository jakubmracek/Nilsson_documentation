## 1. Prolinkování dalších souborů

Pokud chceš vazby v grafu dále rozšiřovat, máš dvě elegantní metody – automatickou přes tvůj skript a poloautomatickou přímo v Obsidianu.

### Metoda A: Rozšíření tvého Python skriptu

Kdykoliv narazíš na nový koncept, entitu nebo modul (např. _„Spisovka“_, _„Výkazy“_), stačí udělat toto:

1. Otevři svůj soubor `autolink.py`.
    
2. Do slovníku `KEYWORDS` přidej nové řádky ve formátu `"skloňovaný tvar": "Master Název Poznámky"`.
    
3. Nezapomeň na pravidlo: **delší a víceslovné tvary dávej ve slovníku výše** než jednoslovné.
    
4. Spusť skript znovu. Projede celý vault a doplní nové linky tam, kde ještě nejsou. Git pak změny sám po 20 minutách odešle.
    

### Metoda B: Rodilé „Nezmíněné odkazy“ (Unlinked Mentions)

Obsidian tohle umí hledat i sám bez skriptů. Když si otevřeš jakoukoliv master poznámku (např. _Třídní kniha_) a podíváš se dolů do té sekce zpětných odkazů, kterou jsme zapínali, uvidíš tam dvě záložky:

- **Linked mentions** (Zmíněné odkazy) – ty, které už mají `[[...]]`.
    
- **Unlinked mentions** (Nezmíněné odkazy) – Obsidian prohledá vault a ukáže ti: _„Hele, v těchto třech souborech se píše slovo 'třídní kniha', ale nemáš tam odkaz.“_ U každého nálezu máš tlačítko **Link**, kterým z toho uděláš odkaz jedním kliknutím.
    

## 2. Jak nechat AI hledat v dokumentaci

Hledání detailů a souvislostí v lokálních markdown souborech je dneska už skvěle vyřešené. Podle toho, kde nejraději pracuješ, se nabízejí tři nejlepší cesty:

### Možnost 1: Přímo uvnitř Obsidianu (Pluginy)

Nemusíš z aplikace vůbec odcházet. Skvělé jsou dva komunitní pluginy:

- **Smart Connections:** Tento plugin si indexuje tvůj vault (vytvoří lokální embeddings). V bočním panelu pak máš chatovací okno, kde se můžeš zeptat: _„Jak máme v Nilssonu vyřešené workflow pro omluvenky, když žák chybí v družině?“_ AI projde soubory a vytáhne ti syntézu i s odkazy na konkrétní řádky.
    
- **Copilot for Obsidian:** Velmi populární plugin. Můžeš ho napojit na API klíč (OpenAI, Anthropic nebo Google Gemini) a v chatu používat příkazy jako `@vault` nebo `@current_note`.
    

### Možnost 2: Přes vývojářské prostředí (Cursor / VS Code)

Protože jde o technickou dokumentaci k softwaru a Nilsson má celou strukturu v obyčejných `.md` souborech, můžeš celou složku vaultu jednoduše otevřít v **Cursoru** nebo **VS Code** s rozšiřováním GitHub Copilot.

- V chatu Cursoru stačí zmáčknout `@` a vybrat **Folder** (nebo celou codebase).
    
- Dotaz: `@dokumentace Jak se chová matice oprávnění pro modul Tripartity?`
    
- AI má okamžitý kontext nad celým stromem souborů a sype ti přesné odpovědi včetně ukázek markdownu.
    

### Možnost 3: Google NotebookLM (Bez nastavování, webové rozhraní)

Pokud nechceš řešit žádné API klíče a instalace, geniální služba je **NotebookLM** od Googlu (je zdarma).

1. Vyexportuješ nebo prostě vezmeš složku s poznámkami z disku.
    
2. Nahraješ ty `.md` soubory jako zdroj do NotebookLM.
    
3. Google z nich vytvoří uzavřenou privátní databázi. Můžeš se pak ptát na nejmenší detaily, nechat si generovat průvodce, nebo si dokonce nechat vytvořit "audio podcast", kde dva AI moderátoři diskutují o architektuře tvého školního systému.
    

Která z těch variant AI vyhledávání ti nejvíce sedí do tvého stávajícího workflow – raději bys to klofal přímo v Obsidianu, nebo ti dává větší smysl otevřít ty markdowny v editoru vedle kódu?