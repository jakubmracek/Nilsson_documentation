import os
import re

# SLOVNÍK KLÍČOVÝCH SLOV
# Vlevo: co skript hledá v textu (case-sensitive, doporučuji zadat i skloňované tvary)
# Vpravo: přesný název poznámky v Obsidianu, na kterou to ukáže.
KEYWORDS = {
    # ── 1. VÍCESLOVNÉ MODULY A FRÁZE (Musí být první kvůli správnému nahrazování) ──
    "Mapa pokroku": "Mapa pokroku",
    "mapa pokroku": "Mapa pokroku",
    "mapy pokroku": "Mapa pokroku",
    "mapě pokroku": "Mapa pokroku",
    "mapu pokroku": "Mapa pokroku",
    "mapou pokroku": "Mapa pokroku",
    "mapách pokroku": "Mapa pokroku",

    "Třídní kniha": "Třídní kniha",
    "třídní kniha": "Třídní kniha",
    "třídní knihy": "Třídní kniha",
    "třídní knize": "Třídní kniha",
    "třídní knihu": "Třídní kniha",
    "třídní knihou": "Třídní kniha",
    "třídních knihách": "Třídní kniha",
    "třídním knihám": "Třídní kniha",

    "Školní družina": "Školní družina",
    "školní družina": "Školní družina",
    "školní družiny": "Školní družina",
    "školní družině": "Školní družina",
    "školní družinu": "Školní družina",
    "školní družinou": "Školní družina",

    "Uzavření pololetí": "Uzavření pololetí",
    "uzavření pololetí": "Uzavření pololetí",
    "uzavřením pololetí": "Uzavření pololetí",

    "MŠMT výkazy": "MŠMT výkazy",
    "mšmt výkazy": "MŠMT výkazy",
    "MŠMT výkaz": "MŠMT výkaz",
    "výkazy MŠMT": "MŠMT výkazy",
    "výkazů MŠMT": "MŠMT výkazy",

    "Správa školy": "Správa školy",
    "správa školy": "Správa školy",
    "správy školy": "Správa školy",
    "správě školy": "Správa školy",
    "správu školy": "Správa školy",
    "správou školy": "Správa školy",

    "Můj profil": "Můj profil",
    "můj profil": "Můj profil",
    "mého profilu": "Můj profil",
    "mém profilu": "Můj profil",

    "Výchovný poradce": "Výchovný poradce (VP)",
    "výchovný poradce": "Výchovný poradce (VP)",
    "výchovného poradce": "Výchovný poradce (VP)",
    "výchovnému poradci": "Výchovný poradce (VP)",
    "výchovném poradci": "Výchovný poradce (VP)",
    "výchovným poradcem": "Výchovný poradce (VP)",

    "Rodičovský portál": "Rodičovský portál",
    "rodičovský portál": "Rodičovský portál",
    "rodičovského portálu": "Rodičovský portál",
    "rodičovskému portálu": "Rodičovský portál",
    "rodičovském portálu": "Rodičovský portál",
    "rodičovským portálem": "Rodičovský portál",

    "Zprávy a nástěnka": "Zprávy a bulletin",
    "zprávy a nástěnka": "Zprávy a bulletin",

    # ── 2. JEDNOSLOVNÉ MODULY A SYNONYMA ──
    "Žáci": "Žáci",
    "žáci": "Žáci",
    "žáků": "Žáci",
    "žákům": "Žáci",
    "žáky": "Žáci",
    "žácích": "Žáci",
    "žáka": "Žáci",

    "Omluvenky": "Omluvenky",
    "omluvenky": "Omluvenky",
    "omluvenka": "Omluvenky",
    "omluvence": "Omluvenky",
    "omluvenku": "Omluvenky",
    "omluvenkou": "Omluvenky",
    "omluvenek": "Omluvenky",
    "omluvenkám": "Omluvenky",
    "omluvenkách": "Omluvenky",

    "Docházka": "Docházka",
    "docházka": "Docházka",
    "docházky": "Docházka",
    "docházce": "Docházka",
    "docházku": "Docházka",
    "docházkou": "Docházka",
    "docházkách": "Docházka",

    "Družina": "Školní družina",
    "družina": "Školní družina",
    "družiny": "Školní družina",
    "družině": "Školní družina",
    "družinu": "Školní družina",
    "družinou": "Školní družina",
    "družinách": "Školní družina",

    "Třídnice": "Třídní kniha",
    "třídnice": "Třídní kniha",
    "třídnici": "Třídní kniha",
    "třídnicí": "Třídní kniha",
    "třídnic": "Třídní kniha",

    "BOZP": "BOZP",
    "bozp": "BOZP",

    "Platby": "Platby",
    "platby": "Platby",
    "platba": "Platby",
    "platbě": "Platby",
    "platbu": "Platby",
    "platbou": "Platby",
    "plateb": "Platby",
    "platbám": "Platby",
    "platbách": "Platby",

    "VP": "Výchovný poradce (VP)",
    "vp": "Výchovný poradce (VP)",

    "Zprávy": "Zprávy a bulletin",
    "zprávy": "Zprávy a bulletin",
    "zpráva": "Zprávy a bulletin",
    "zprávě": "Zprávy a bulletin",
    "zprávu": "Zprávy a bulletin",
    "zprávou": "Zprávy a bulletin",
    "zpráv": "Zprávy a bulletin",
    "zprávám": "Zprávy a bulletin",
    "zprávách": "Zprávy a bulletin",

    "Bulletin": "Zprávy a bulletin",
    "bulletin": "Zprávy a bulletin",
    "bulletiny": "Zprávy a bulletin",
    "bulletinu": "Zprávy a bulletin",

    "Nástěnka": "Zprávy a bulletin",
    "nástěnka": "Zprávy a bulletin",
    "nástěnky": "Zprávy a bulletin",
    "nástěnce": "Zprávy a bulletin",
    "nástěnku": "Zprávy a bulletin",
    "nástěnkou": "Zprávy a bulletin",
    "nástěnek": "Zprávy a bulletin",

    "Tripartity": "Tripartity",
    "tripartity": "Tripartity",
    "tripartita": "Tripartity",
    "tripartitě": "Tripartity",
    "tripartitu": "Tripartity",
    "tripartitou": "Tripartity",
    "tripartit": "Tripartity",
    "tripartitám": "Tripartity",
    "tripartitách": "Tripartity",

    "Spisovka": "Spisovka",
    "spisovka": "Spisovka",
    "spisovky": "Spisovka",
    "spisovce": "Spisovka",
    "spisovku": "Spisovka",
    "spisovkou": "Spisovka",
    "spisovek": "Spisovka",

    "Souhlasy": "Souhlasy",
    "souhlasy": "Souhlasy",
    "souhlas": "Souhlasy",
    "souhlasu": "Souhlasy",
    "souhlasem": "Souhlasy",
    "souhlasů": "Souhlasy",
    "souhlasům": "Souhlasy",
    "souhlasech": "Souhlasy",

    "Portál": "Rodičovský portál",
    "portál": "Rodičovský portál",
    "portálu": "Rodičovský portál",
    "portálem": "Rodičovský portál",
    "portály": "Rodičovský portál",
    "portálech": "Rodičovský portál",
    
    "Přehled": "Přehled",
    "přehled": "Přehled",
    "přehledu": "Přehled",
    "Dashboard": "Přehled",
    "dashboard": "Přehled",
    
    "Nastavení": "Nastavení",
    "nastavení": "Nastavení"
}

# Skript běží přímo v aktuální složce
FOLDER_PATH = "."

def auto_link_files():
    print("Spouštím automatické prolinkování...")
    count_modified = 0
    
    for filename in os.listdir(FOLDER_PATH):
        # Ignorujeme samotný skript a systémové složky Gitu/Obsidianu
        if filename.endswith(".md") and not filename.startswith("."):
            file_path = os.path.join(FOLDER_PATH, filename)
            
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            original_content = content

            # Projdeme všechna klíčová slova ze slovníku
            for kw, note_name in KEYWORDS.items():
                # Trik s regexem: najde slovo, jen pokud kolem něj nejsou hranaté závorky nebo jiná písmena
                pattern = rf'(?<!\[\[)(?<!\w){kw}(?!\w)(?!\]\])'
                content = re.sub(pattern, f'[[{note_name}]]', content)

            # Pokud došlo ke změně, soubor přepíšeme
            if content != original_content:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)
                print(f" Prolinkováno: {filename}")
                count_modified += 1
                
    print(f"\nHotovovo! Změněno {count_modified} souborů.")

if __name__ == "__main__":
    auto_link_files()