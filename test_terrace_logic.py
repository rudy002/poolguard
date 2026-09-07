"""Teste la machine a etats de la pre-alerte terrasse, sans camera ni GPU."""
import sys, time
sys.path.insert(0,'/ssd/poolguard')
import poolguard_alert as P

declenchements = []
P.declencher_alerte_terrasse = lambda box: declenchements.append(box)
P.log_event = lambda *a, **k: None

def reset(armed=True, alert=False):
    declenchements.clear()
    P.ARMED = armed; P.alert_active = alert
    P.terrace_entry_time = None
    P.last_person_on_terrace_time = 0.0
    P.last_terrace_alert_time = 0.0
    P.terrace_alert_done_this_visit = False
    P.terrace_box = [1100, 502, 1209, 709]

T0 = time.time()          # base realiste : le code compare a time.time()

def av(t, present=True):
    P.check_terrace_prealert({'TERRACE': 1 if present else 0}, T0 + t)

ok = lambda c,n: print(f"  {'OK  ' if c else 'ECHEC'} {n}")
tout = []

# 1. presence continue 3 s -> 1 alerte
reset(); [av(t) for t in (0,1,2,3.1)]
tout.append(len(declenchements)==1); ok(tout[-1], "presence 3 s -> 1 alerte")

# 2. moins de 3 s -> aucune alerte
reset(); [av(t) for t in (0,1,2)]
tout.append(len(declenchements)==0); ok(tout[-1], "presence 2 s -> aucune alerte")

# 3. clignotement (trous < 1,5 s) -> le compteur NE se remet PAS a zero
reset()
for t in (0, 0.5, 1.0): av(t)
av(1.6, present=False)          # trou de 0,6 s
for t in (2.0, 3.1): av(t)
tout.append(len(declenchements)==1); ok(tout[-1], "clignotement absorbe -> alerte quand meme")

# 4. vraie sortie (> 1,5 s) -> compteur remis a zero
reset()
for t in (0,1,2): av(t)
for t in (4.0, 5.0): av(t, present=False)   # 3 s d'absence
av(5.5); av(6.5)                             # nouvelle entree, 1 s seulement
tout.append(len(declenchements)==0); ok(tout[-1], "vraie sortie -> compteur reinitialise")

# 5. anti-spam : 2e alerte refusee avant 120 s
reset(); [av(t) for t in (0,1,2,3.1)]
for t in (10,11,12,13.1): av(t)
tout.append(len(declenchements)==1); ok(tout[-1], "anti-spam : pas de 2e alerte a t+10s")

# 6. plancher de securite : meme si le drapeau "deja prevenu" saute (ex: redemarrage
#    du service), le delai de 120 s empeche une rafale.
reset(); [av(t) for t in (0,1,2,3.1)]
P.terrace_alert_done_this_visit = False      # simule une reinitialisation
for t in (60,61,62,63.1): av(t)              # 60 s plus tard : sous le plancher
tout.append(len(declenchements)==1)
ok(tout[-1], f"plancher 120 s tient meme si le drapeau saute (obtenu: {len(declenchements)})")

# 7. systeme desarme -> rien
reset(armed=False); [av(t) for t in (0,1,2,3.1)]
tout.append(len(declenchements)==0); ok(tout[-1], "systeme desarme -> aucune alerte")

# 8. alerte piscine deja active -> pre-alerte supprimee
reset(alert=True); [av(t) for t in (0,1,2,3.1)]
tout.append(len(declenchements)==0); ok(tout[-1], "alerte piscine active -> pre-alerte supprimee")

# 9. pas de boite englobante -> pas d'alerte (on n'envoie pas une photo sans cible)
reset(); P.terrace_box=None; [av(t) for t in (0,1,2,3.1)]
tout.append(len(declenchements)==0); ok(tout[-1], "aucune boite -> pas d'alerte")

# 10. la logique piscine n'est pas affectee
reset()
avant = (P.ARMED, P.alert_active, P.pool_entry_time)
[av(t) for t in (0,1,2,3.1)]
tout.append((P.ARMED,P.alert_active,P.pool_entry_time)==avant)
ok(tout[-1], "etat de l'alarme piscine inchange")

# 11. NON-REGRESSION du bug constate en production le 2026-09-06 :
#     quelqu'un qui RESTE sur la terrasse ne doit generer QU'UNE alerte,
#     pas une toutes les 2 minutes (13 photos en 29 min avant correction).
reset()
for t in range(0, 1800, 5):          # 30 minutes de presence continue
    av(t)
tout.append(len(declenchements)==1)
ok(tout[-1], f"presence continue 30 min -> 1 seule alerte (obtenu: {len(declenchements)})")

# 12. la terrasse se vide puis quelqu'un revient -> nouvelle alerte autorisee
reset()
for t in (0,1,2,3.1): av(t)                       # 1er passage -> alerte
for t in range(10, 400, 5): av(t, present=False)  # terrasse vide 6.5 min
for t in (400,401,402,403.1): av(t)               # 2e passage
tout.append(len(declenchements)==2)
ok(tout[-1], f"nouveau passage apres 5 min de vide -> 2e alerte (obtenu: {len(declenchements)})")

# 13. absence trop courte (2 min) -> PAS de nouvelle alerte
reset()
for t in (0,1,2,3.1): av(t)
for t in range(10, 130, 5): av(t, present=False)  # vide 2 min seulement
for t in (130,131,132,133.1): av(t)
tout.append(len(declenchements)==1)
ok(tout[-1], f"absence de 2 min -> pas de 2e alerte (obtenu: {len(declenchements)})")

print(f"\n{sum(tout)}/{len(tout)} tests passes")
sys.exit(0 if all(tout) else 1)
