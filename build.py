# -*- coding: utf-8 -*-
"""
Сборщик утренней сводки «Наши в НХЛ».
Берёт открытые данные с api-web.nhle.com, находит россиян и пишет index.html.
Запускается GitHub Actions по расписанию (см. .github/workflows/update.yml)
или вручную: python build.py
"""
import json, re, sys, urllib.request, urllib.error
from datetime import datetime, timedelta, timezone

API = "https://api-web.nhle.com/v1"
EKB = timezone(timedelta(hours=5))          # Екатеринбург
TEMPLATE = "template.html"
OUT = "index.html"

# ---------- справочники ----------
CLUBS = {
 "ANA":"Анахайм","BOS":"Бостон","BUF":"Баффало","CAR":"Каролина","CBJ":"Коламбус","CGY":"Калгари",
 "CHI":"Чикаго","COL":"Колорадо","DAL":"Даллас","DET":"Детройт","EDM":"Эдмонтон","FLA":"Флорида",
 "LAK":"Лос-Анджелес","MIN":"Миннесота","MTL":"Монреаль","NJD":"Нью-Джерси","NSH":"Нэшвилл",
 "NYI":"Айлендерс","NYR":"Рейнджерс","OTT":"Оттава","PHI":"Филадельфия","PIT":"Питтсбург",
 "SEA":"Сиэтл","SJS":"Сан-Хосе","STL":"Сент-Луис","TBL":"Тампа-Бэй","TOR":"Торонто","UTA":"Юта",
 "VAN":"Ванкувер","VGK":"Вегас","WPG":"Виннипег","WSH":"Вашингтон",
}
# русские имена по английской фамилии (fallback — английское имя)
RU = {
 "Mintyukov":"Павел Минтюков","Zadorov":"Никита Задоров","Khusnutdinov":"Марат Хуснутдинов",
 "Ovechkin":"Александр Овечкин","Miroshnichenko":"Иван Мирошниченко","Barbashev":"Иван Барбашёв",
 "Namestnikov":"Владислав Наместников","Tarasov":"Даниил Тарасов","Kuznetsov":"Ян Кузнецов",
 "Gridin":"Матвей Гридин","Tsyplakov":"Максим Цыплаков","Suniev":"Айдар Суниев","Kochetkov":"Пётр Кочетков",
 "Svechnikov":"Андрей Свечников","Provorov":"Иван Проворов","Nichushkin":"Валерий Ничушкин",
 "Voronkov":"Дмитрий Воронков","Svechkov":"Фёдор Свечков","Panarin":"Артемий Панарин",
 "Kaprizov":"Кирилл Капризов","Yurov":"Данила Юров","Shabanov":"Максим Шабанов","Trenin":"Яков Тренин",
 "Demidov":"Иван Демидов","Gritsyuk":"Арсений Грицюк","Sorokin":"Илья Сорокин","Varlamov":"Семён Варламов",
 "Romanov":"Александр Романов","Shesterkin":"Игорь Шестёркин","Gavrikov":"Владислав Гавриков",
 "Dorofeyev":"Павел Дорофеев","Lyubushkin":"Илья Любушкин","Zub":"Артём Зуб","Murashov":"Сергей Мурашов",
 "Malkin":"Евгений Малкин","Chinakhov":"Егор Чинахов","Kuzmenko":"Андрей Кузьменко","Askarov":"Ярослав Аскаров",
 "Orlov":"Дмитрий Орлов","Chernyshov":"Игорь Чернышов","Buchnevich":"Павел Бучневич","Toropchenko":"Алексей Торопченко",
 "Vasilevskiy":"Андрей Василевский","Kucherov":"Никита Кучеров","Mikheyev":"Илья Михеев","Bobrovsky":"Сергей Бобровский",
 "Marchenko":"Кирилл Марченко","Kulikov":"Дмитрий Куликов","Michkov":"Матвей Мичков","Grebenkin":"Никита Гребенкин",
 "Kantserov":"Роман Канцеров","Mukhamadullin":"Шакир Мухамадуллин","Podkolzin":"Василий Подколзин",
 "Sergachev":"Михаил Сергачёв","Simashev":"Дмитрий Симашев","But":"Даниил Бут","Georgiev":"Александр Георгиев",
 "Samsonov":"Илья Самсонов","Chibrikov":"Никита Чибриков","Afanasyev":"Егор Афанасьев","Zamula":"Егор Замула",
 "Kuzmin":"Кирилл Кузьмин","Yakemchuk":"Данил Якемчук","Amirov":"Родион Амиров",
}
POS = {"G":"в","D":"з","C":"н","L":"н","R":"н"}
STRENGTH = {"pp":"большинство","sh":"меньшинство","ev":"равные составы"}
TEAM_IDS = {}   # abbrev -> id (заполняется по ходу)


def get(path, default=None):
    url = API + path
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent":"nashi-v-nhl/1.0"}), timeout=30) as r:
            return json.load(r)
    except Exception as e:  # noqa
        print("! не удалось:", url, e, file=sys.stderr)
        return default


def name_of(p):
    """русское имя игрока по объекту из ростера/бокскора"""
    last = (p.get("lastName") or {}).get("default") if isinstance(p.get("lastName"), dict) else p.get("lastName")
    first = (p.get("firstName") or {}).get("default") if isinstance(p.get("firstName"), dict) else p.get("firstName")
    if not last and isinstance(p.get("name"), dict):
        nm = p["name"].get("default", "")
        last = nm.split(" ")[-1]; first = nm.split(" ")[0]
    return RU.get(last or "", f"{first or ''} {last or ''}".strip())


def toi_str(t):
    return t if isinstance(t, str) else "—"


# ---------- 1. россияне по всем клубам ----------
def load_russians():
    """{playerId: {name, club, pos, abbrev}} по текущим ростерам"""
    rus = {}
    for abbrev in CLUBS:
        roster = get(f"/roster/{abbrev}/current", {}) or {}
        for group in ("forwards", "defensemen", "goalies"):
            for p in roster.get(group, []):
                if p.get("birthCountry") == "RUS":
                    rus[p["id"]] = {"name": name_of(p), "club": CLUBS[abbrev], "abbrev": abbrev,
                                    "pos": POS.get(p.get("positionCode"), "н")}
    return rus


def season_line(pid, is_goalie):
    """строка за сезон из карточки игрока"""
    d = get(f"/player/{pid}/landing", {}) or {}
    fs = ((d.get("featuredStats") or {}).get("regularSeason") or {}).get("subSeason") or {}
    status = ""
    if is_goalie:
        gp = fs.get("gamesPlayed"); sv = fs.get("savePctg"); gaa = fs.get("goalsAgainstAvg"); so = fs.get("shutouts")
        if gp:
            status = f"{gp} " + ("матч" if gp%10==1 and gp!=11 else "матча" if 1<gp%10<5 and not 11<gp<15 else "матчей") + f", {sv*100:.1f}% сейвов, КН {gaa:.2f}" + (f", «сухих» {so}" if so else "")
    else:
        gp = fs.get("gamesPlayed"); g = fs.get("goals"); a = fs.get("assists"); pm = fs.get("plusMinus")
        if gp:
            status = f"{g}+{a} в {gp} " + ("матче" if gp==1 else "матчах") + (f", +/- {pm:+d}" if isinstance(pm, int) else "")
    return status or "в этом сезоне ещё не играл"


# ---------- 2. матчи за игровой день ----------
def game_day():
    """дата игрового дня по-североамерикански: до 14:00 UTC считаем, что это ещё «вчерашняя ночь»"""
    now = datetime.now(timezone.utc)
    return (now - timedelta(hours=14)).date()


def load_games(date):
    sc = get(f"/score/{date.isoformat()}", {}) or {}
    return [g for g in sc.get("games", []) if g.get("gameState") in ("OFF", "FINAL", "LIVE", "CRIT")]


def attacking_right(play, home_id, team_id):
    """true, если команда атакует вправо (в координатах НХЛ x>0)"""
    side = play.get("homeTeamDefendingSide", "left")  # куда защищаются хозяева
    home_attacks_right = side == "left"
    return home_attacks_right if team_id == home_id else not home_attacks_right


def goal_schemes(game_id, home_id, rus):
    """схемы голов россиян по play-by-play: координаты броска"""
    pbp = get(f"/gamecenter/{game_id}/play-by-play", {}) or {}
    out = []
    for pl in pbp.get("plays", []):
        if pl.get("typeDescKey") != "goal":
            continue
        d = pl.get("details", {})
        sid = d.get("scoringPlayerId")
        if sid not in rus:
            continue
        x, y = d.get("xCoord"), d.get("yCoord")
        if x is None or y is None:
            x, y = 70, 0
        if not attacking_right(pl, home_id, d.get("eventOwnerTeamId")):
            x, y = -x, -y
        px = max(30, min(368, 200 + x * 1.9)); py = max(14, min(156, 85 - y * 1.85))
        period = pl.get("periodDescriptor", {}).get("number", 0)
        ptxt = {1:"1-й период",2:"2-й период",3:"3-й период"}.get(period, "овертайм")
        sit = pl.get("situationCode", "1551")  # away goalie, away skaters, home skaters, home goalie
        empty = False
        try:
            # ворота соперника пустые: у соперника вратарь = 0
            is_home = d.get("eventOwnerTeamId") == home_id
            empty = (sit[0] == "0") if is_home else (sit[3] == "0")
            own = int(sit[2] if is_home else sit[1]); opp = int(sit[1] if is_home else sit[2])
            strength = "" if empty else "большинство" if own > opp else "меньшинство" if own < opp else ""
        except Exception:
            strength = ""
        assists = [rus[a]["name"] if a in rus else (d.get(k + "Name", {}) or {}).get("default", "") 
                   for k, a in (("assist1Player", d.get("assist1PlayerId")), ("assist2Player", d.get("assist2PlayerId"))) if a]
        assists = [a for a in assists if a]
        shot = {"wrist":"кистевой","slap":"щелчок","snap":"с кистей","backhand":"с неудобной","tip-in":"подставление",
                "deflected":"рикошет","wrap-around":"из-за ворот"}.get(d.get("shotType",""), "")
        bits = [ptxt, pl.get("timeInPeriod","")]
        if strength: bits.append(strength)
        if empty: bits.append("пустые ворота")
        via = []
        if shot: via.append(f"Бросок: {shot}")
        if assists: via.append("Передачи: " + ", ".join(assists))
        sc = f"{d.get('homeScore','')}:{d.get('awayScore','')}"
        out.append({"pid": sid, "t": ", ".join(b for b in bits if b) + f" — счёт стал {sc}",
                    "via": ". ".join(via) if via else "Без передач",
                    "shot": {"x": round(px), "y": round(py), "n": rus[sid]["name"].split()[-1][:3].upper()},
                    "empty": empty})
    return out


def load_logos():
    """{русское имя клуба: url логотипа} из таблицы лиги"""
    out = {}
    st = get("/standings/now", {}) or {}
    for t in st.get("standings", []):
        ab = t.get("teamAbbrev", {}).get("default"); url = t.get("teamLogo")
        if ab in CLUBS and url:
            out[CLUBS[ab]] = url
    return out


def build():
    rus = load_russians()
    logos = load_logos()
    date = game_day()
    games = load_games(date)
    skaters, goalies, results, moments = [], [], [], []
    per_player = {}   # pid -> {g,a,...}
    ru_goals_total = 0

    for g in games:
        gid = g["id"]; home = g["homeTeam"]; away = g["awayTeam"]
        home_id = home.get("id"); TEAM_IDS[home["abbrev"]] = home_id
        hs, as_ = home.get("score", 0), away.get("score", 0)
        suffix = {"OT":"ОТ","SO":"Б"}.get((g.get("periodDescriptor") or {}).get("periodType",""), "")
        if g.get("gameState") in ("LIVE","CRIT"): suffix = "идёт"
        box = get(f"/gamecenter/{gid}/boxscore", {}) or {}
        pbg = box.get("playerByGameStats", {})
        ru_in_game = []
        for side_key, team in (("homeTeam", home), ("awayTeam", away)):
            club = CLUBS.get(team["abbrev"], team["abbrev"])
            for grp in ("forwards", "defense"):
                for p in pbg.get(side_key, {}).get(grp, []):
                    if p.get("playerId") in rus:
                        nm = rus[p["playerId"]]["name"]
                        gl, a = p.get("goals",0), p.get("assists",0)
                        skaters.append([nm, club, f"{gl}+{a}", p.get("sog",0), toi_str(p.get("toi"))])
                        per_player[p["playerId"]] = {"g":gl,"a":a,"club":club,"home":home,"away":away,"hs":hs,"as":as_,"suffix":suffix,"gid":gid}
                        ru_goals_total += gl
                        tag = f"{nm.split()[-1]} — {gl} гол" + ("а" if 1<gl<5 else "") if gl else (f"{nm.split()[-1]} — пас" if a else nm.split()[-1])
                        ru_in_game.append(tag)
            for p in pbg.get(side_key, {}).get("goalies", []):
                if p.get("playerId") in rus and p.get("toi") not in (None, "00:00"):
                    nm = rus[p["playerId"]]["name"]
                    sa = p.get("shotsAgainst") or 0; ga = p.get("goalsAgainst") or 0
                    sv = sa - ga
                    pct = f"{(sv/sa*100):.1f}%" if sa else "—"
                    goalies.append([nm, club, f"{sv} из {sa}", pct])
                    per_player[p["playerId"]] = {"goalie":True,"sv":sv,"sa":sa,"pct":pct,"club":club,"home":home,"away":away,"hs":hs,"as":as_,"suffix":suffix,"gid":gid}
                    ru_in_game.append(f"{nm.split()[-1]} {sv}/{sa}")
        results.append([CLUBS.get(home["abbrev"],home["abbrev"]), CLUBS.get(away["abbrev"],away["abbrev"]), hs, as_, suffix, "; ".join(ru_in_game) or "—"])

        # схемы голов
        if any(v.get("g") for v in per_player.values() if v.get("gid")==gid):
            schemes = goal_schemes(gid, home_id, rus)
            by_pid = {}
            for s in schemes: by_pid.setdefault(s["pid"], []).append(s)
            for pid, items in by_pid.items():
                info = per_player.get(pid, {})
                hn, an = CLUBS.get(home["abbrev"],home["abbrev"]), CLUBS.get(away["abbrev"],away["abbrev"])
                score = f"{hn} — {an}"; res = f"{hs}:{as_}" + (f" {suffix}" if suffix else "")
                n = max(len(items), info.get("g", 0))
                moments.append({"who": rus[pid]["name"], "club": rus[pid]["club"],
                    "badge": ["goal", f"{info.get('g',n)}+{info.get('a',0)}"],
                    "what": ("Хет-трик! " if n>=3 else "Дубль. " if n==2 else "") + f"{n} " + ("гол" if n==1 else "гола" if n<5 else "голов") + f" в матче {score} {res}.",
                    "score": score, "res": res,
                    "yt": f"{home['abbrev']} {away['abbrev']} highlights {date.isoformat()} {rus[pid]['name']}",
                    "ya": f"{hn} {an} обзор матча {rus[pid]['name']} голы",
                    "goals": [{k:v for k,v in it.items() if k!="pid"} for it in items]})

    # «ещё за ночь»: передачи без голов и вратари
    for pid, v in per_player.items():
        hn, an = CLUBS.get(v["home"]["abbrev"]), CLUBS.get(v["away"]["abbrev"])
        score = f"{hn} — {an}"; res = f"{v['hs']}:{v['as']}" + (f" {v['suffix']}" if v['suffix'] else "")
        if v.get("goalie"):
            if v["sa"] >= 20 or (v["sa"] and v["sv"]==v["sa"]):
                moments.append({"who": rus[pid]["name"], "club": v["club"], "badge":["save", f"{v['sv']}/{v['sa']}"],
                    "what": ("«Сухой» матч! " if v["sv"]==v["sa"] and v["sa"] else "") + f"Отразил {v['sv']} бросков из {v['sa']} ({v['pct']}).",
                    "score": score, "res": res, "yt": f"{v['home']['abbrev']} {v['away']['abbrev']} highlights {date.isoformat()}", "ya": f"{hn} {an} обзор матча"})
        elif not v.get("g") and v.get("a"):
            moments.append({"who": rus[pid]["name"], "club": v["club"], "badge":["assist", f"0+{v['a']}"],
                "what": f"{v['a']} результативн" + ("ая передача" if v['a']==1 else "ые передачи" if v['a']<5 else "ых передач") + ".",
                "score": score, "res": res, "yt": f"{v['home']['abbrev']} {v['away']['abbrev']} highlights {date.isoformat()}", "ya": f"{hn} {an} обзор матча"})

    # сортировка: сначала голы (больше — выше), потом остальное
    moments.sort(key=lambda m: (-(len(m.get("goals",[]))), m["badge"][0]!="goal"))
    skaters.sort(key=lambda r: (-int(r[2].split("+")[0])*2 - int(r[2].split("+")[1]), r[0]))

    # ближайшая ночь
    nxt = get(f"/schedule/{(date+timedelta(days=1)).isoformat()}", {}) or {}
    tonight = []
    for day in nxt.get("gameWeek", [])[:1]:
        for g in day.get("games", []):
            ha, aa = g["homeTeam"]["abbrev"], g["awayTeam"]["abbrev"]
            try:
                t = datetime.fromisoformat(g["startTimeUTC"].replace("Z","+00:00")).astimezone(EKB).strftime("%H:%M")
            except Exception:
                t = ""
            ours = [v["name"].split()[-1] for v in rus.values() if v["abbrev"] in (ha, aa)]
            tonight.append([CLUBS.get(ha,ha), CLUBS.get(aa,aa), t, ", ".join(ours) or "наших нет"])

    # состав по клубам + сезон
    roster = {}
    for pid, v in rus.items():
        roster.setdefault(v["club"], []).append([v["name"], v["pos"], "", season_line(pid, v["pos"]=="в")])
    roster_list = [[club, sorted(ps, key=lambda p: ("взн".index(p[1]), p[0]))] for club, ps in sorted(roster.items())]

    data = {
        "updated": datetime.now(EKB).strftime("%d.%m.%Y %H:%M") + " (Екб)",
        "night": f"матчи в ночь на {(date+timedelta(days=1)).strftime('%d.%m')}",
        "totals": [[str(len(games)), "матчей"], [str(len(set(r[0] for r in skaters)|set(r[0] for r in goalies))), "россиян на льду"], [str(ru_goals_total), "шайб наших"]],
        "moments": moments, "skaters": skaters, "goalies": goalies, "games": results, "tonight": tonight,
        "roster": roster_list, "logos": logos,
        "source": {"title": "официальные данные НХЛ (api-web.nhle.com)", "url": "https://www.nhl.com/scores"},
    }
    return data


if __name__ == "__main__":
    data = build()
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    tpl = open(TEMPLATE, encoding="utf-8").read()
    html = tpl.replace("/*__DATA__*/", "const DATA = " + json.dumps(data, ensure_ascii=False) + ";")
    open(OUT, "w", encoding="utf-8").write(html)
    print("готово:", OUT, "| матчей:", len(data["games"]), "| моментов:", len(data["moments"]))
