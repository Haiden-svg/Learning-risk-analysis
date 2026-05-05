r"""
MCTS — Exemple pédagogique simple
==================================
Problème : trouver le chemin le moins coûteux dans un graphe orienté pondéré.

Le graphe représente un réseau de villes avec des coûts de déplacement.
L'objectif est d'aller de la ville S (Start) à la ville G (Goal).

Graphe utilisé :
                    S
                   / \
                 (1)  (4)
                 /     \
                A       B
               / \       \
             (2) (5)     (1)
             /     \       \
            C       D       G  ← OBJECTIF
           /         \
         (3)          (2)
         /             \
        G               G

Coûts des chemins :
  S→A→C→G  = 1+2+3 = 6   ← OPTIMAL
  S→A→D→G  = 1+5+2 = 8
  S→B→G    = 4+1   = 5   ← mais ce chemin doit être découvert aussi

Comparaison :
  - Dijkstra : explore TOUS les nœuds par ordre de coût croissant (garantit l'optimal)
  - MCTS     : explore intelligemment via UCB1, trouve une bonne solution rapidement
               sans explorer tout l'espace — utile quand l'espace est ÉNORME.
r"""

from __future__ import annotations

import math
import random
import time
from typing import Optional


# ══════════════════════════════════════════════════════════════════════════════
# 1. DÉFINITION DU GRAPHE
# ══════════════════════════════════════════════════════════════════════════════

# Graphe orienté pondéré : {nœud_source: [(nœud_dest, coût), ...]}
GRAPHE = {
    "S": [("A", 1), ("B", 4)],
    "A": [("C", 2), ("D", 5)],
    "B": [("G", 1)],
    "C": [("G", 3)],
    "D": [("G", 2)],
    "G": [],  # nœud terminal (objectif)
}

DEPART  = "S"
OBJECTIF = "G"

# Coûts de référence (Dijkstra optimal)
COUTS_REFERENCE = {
    "S→A→C→G": 6,
    "S→A→D→G": 8,
    "S→B→G":   5,
}


# ══════════════════════════════════════════════════════════════════════════════
# 2. NŒUD MCTS
# ══════════════════════════════════════════════════════════════════════════════

class Noeud:
    """
    Un nœud de l'arbre MCTS.

    Attributs clés :
      - etat        : ville courante dans le graphe
      - visites     : combien de fois ce nœud a été visité
      - recompense  : somme des récompenses reçues lors des simulations
      - enfants     : nœuds fils (actions déjà explorées)
      - actions_restantes : actions pas encore essayées depuis ce nœud
    """

    def __init__(
        self,
        etat:         str,
        parent:       Optional["Noeud"] = None,
        action:       Optional[tuple]   = None,  # (nœud_dest, coût)
        cout_cumule:  int = 0,
    ):
        self.etat        = etat
        self.parent      = parent
        self.action      = action        # transition qui a mené ici
        self.cout_cumule = cout_cumule   # coût depuis la racine

        self.visites    : int   = 0
        self.recompense : float = 0.0
        self.enfants    : list["Noeud"] = []

        # Actions non encore explorées = voisins non encore développés
        self.actions_restantes: list[tuple] = list(GRAPHE.get(etat, []))
        random.shuffle(self.actions_restantes)

    # ── Propriétés ──────────────────────────────────────────────────────────

    def est_terminal(self) -> bool:
        """Sommes-nous à l'objectif ou dans une impasse ?"""
        return self.etat == OBJECTIF or len(GRAPHE.get(self.etat, [])) == 0

    def est_completement_explore(self) -> bool:
        return len(self.actions_restantes) == 0

    # ── UCB1 ────────────────────────────────────────────────────────────────

    def ucb1(self, C: float) -> float:
        """
        Formule UCB1 :
            score = (récompense_moyenne) + C × √(ln(visites_parent) / visites)
                    ─────────────────────   ────────────────────────────────────
                       EXPLOITATION               EXPLORATION

        - Exploitation : préférer les nœuds qui ont donné de bons résultats
        - Exploration  : ne pas négliger les nœuds peu visités
        C = 0   → pur exploitation (avide, peut rater l'optimal)
        C = ∞   → pur exploration (revient à aléatoire)
        C = √2  → équilibre théoriquement optimal (UCB1 classique)
        """
        if self.visites == 0:
            return float("inf")  # nœud jamais visité = priorité absolue
        exploitation = self.recompense / self.visites
        exploration  = C * math.sqrt(math.log(self.parent.visites) / self.visites)
        return exploitation + exploration

    def __repr__(self) -> str:
        moy = self.recompense / self.visites if self.visites > 0 else 0
        return f"Noeud({self.etat}, v={self.visites}, r_moy={moy:.3f}, coût={self.cout_cumule})"


# ══════════════════════════════════════════════════════════════════════════════
# 3. LES 4 PHASES MCTS
# ══════════════════════════════════════════════════════════════════════════════

def selectionner(racine: Noeud, C: float) -> Noeud:
    """
    PHASE 1 — SÉLECTION
    -------------------
    Descend l'arbre en choisissant à chaque niveau l'enfant
    avec le meilleur score UCB1, jusqu'à trouver un nœud
    non complètement exploré ou un nœud terminal.
    """
    noeud = racine
    chemin = [noeud.etat]

    while noeud.est_completement_explore() and not noeud.est_terminal() and noeud.enfants:
        noeud = max(noeud.enfants, key=lambda n: n.ucb1(C))
        chemin.append(noeud.etat)

    return noeud


def expansion(noeud: Noeud) -> Noeud:
    """
    PHASE 2 — EXPANSION
    -------------------
    Crée un nouveau nœud enfant en essayant une action
    non encore explorée depuis ce nœud.
    Retourne le nouveau nœud créé.
    """
    # Prend une action non encore essayée
    dest, cout_action = noeud.actions_restantes.pop()

    enfant = Noeud(
        etat        = dest,
        parent      = noeud,
        action      = (dest, cout_action),
        cout_cumule = noeud.cout_cumule + cout_action,
    )
    noeud.enfants.append(enfant)
    return enfant


def simulation(noeud: Noeud) -> float:
    """
    PHASE 3 — SIMULATION (rollout)
    ------------------------------
    Depuis le nœud courant, joue aléatoirement jusqu'à
    l'objectif ou une impasse. Retourne une récompense.

    Récompense = 1 / coût_total  (plus le chemin est court, mieux c'est)
    Si objectif non atteint → récompense = 0
    """
    etat        = noeud.etat
    cout_total  = noeud.cout_cumule
    profondeur  = 0
    MAX_PROF    = 10  # évite les boucles infinies

    while etat != OBJECTIF and profondeur < MAX_PROF:
        voisins = GRAPHE.get(etat, [])
        if not voisins:
            break
        # Politique aléatoire uniforme (peut être améliorée : heuristique, LCS, etc.)
        dest, cout_action = random.choice(voisins)
        etat       = dest
        cout_total += cout_action
        profondeur += 1

    if etat == OBJECTIF:
        return 1.0 / cout_total   # récompense : inverse du coût
    return 0.0


def retropropagation(noeud: Noeud, recompense: float) -> None:
    """
    PHASE 4 — RÉTROPROPAGATION
    --------------------------
    Remonte la récompense vers la racine en mettant à jour
    les compteurs visites et récompense de chaque nœud ancêtre.
    """
    curseur = noeud
    while curseur is not None:
        curseur.visites    += 1
        curseur.recompense += recompense
        curseur = curseur.parent


# ══════════════════════════════════════════════════════════════════════════════
# 4. ALGORITHME MCTS COMPLET
# ══════════════════════════════════════════════════════════════════════════════

def mcts(
    n_iterations: int  = 100,
    C:            float = math.sqrt(2),
    verbose:      bool  = True,
    graine:       int   = 42,
) -> tuple[list[str], int]:
    """
    Algorithme MCTS complet sur le graphe de villes.

    À chaque itération :
      1. Sélection   : descend l'arbre par UCB1
      2. Expansion   : développe un nœud non encore exploré
      3. Simulation  : rollout aléatoire
      4. Rétroprop.  : met à jour les statistiques

    Retourne le meilleur chemin et son coût.
    """
    random.seed(graine)
    racine = Noeud(DEPART)

    meilleur_cout   = float("inf")
    meilleur_chemin : list[str] = []
    log_iterations  : list[dict] = []

    for i in range(1, n_iterations + 1):

        # ── Phase 1 : Sélection ─────────────────────────────────────────────
        noeud = selectionner(racine, C)

        # ── Phase 2 : Expansion ─────────────────────────────────────────────
        if not noeud.est_terminal() and not noeud.est_completement_explore():
            noeud = expansion(noeud)

        # ── Phase 3 : Simulation ────────────────────────────────────────────
        recompense = simulation(noeud)

        # ── Phase 4 : Rétropropagation ──────────────────────────────────────
        retropropagation(noeud, recompense)

        # ── Extraction du meilleur chemin ───────────────────────────────────
        if noeud.etat == OBJECTIF and noeud.cout_cumule < meilleur_cout:
            meilleur_cout = noeud.cout_cumule
            # Reconstituer le chemin depuis la racine
            chemin = []
            cur = noeud
            while cur is not None:
                chemin.append(cur.etat)
                cur = cur.parent
            meilleur_chemin = list(reversed(chemin))

            log_iterations.append({
                "iter":   i,
                "cout":   meilleur_cout,
                "chemin": " → ".join(meilleur_chemin),
            })

    if verbose:
        _afficher_log(log_iterations, racine, n_iterations)

    return meilleur_chemin, meilleur_cout


# ══════════════════════════════════════════════════════════════════════════════
# 5. DIJKSTRA (pour comparaison)
# ══════════════════════════════════════════════════════════════════════════════

def dijkstra() -> tuple[list[str], int, int]:
    """
    Algorithme de Dijkstra sur le même graphe.
    Garantit l'optimal mais explore TOUS les nœuds accessibles.

    Retourne : (chemin_optimal, coût, nb_noeuds_explores)
    """
    import heapq

    # file de priorité : (coût, nœud, chemin)
    file     = [(0, DEPART, [DEPART])]
    visites  = set()
    explores = 0

    while file:
        cout, noeud, chemin = heapq.heappop(file)

        if noeud in visites:
            continue
        visites.add(noeud)
        explores += 1

        if noeud == OBJECTIF:
            return chemin, cout, explores

        for voisin, cout_arete in GRAPHE.get(noeud, []):
            if voisin not in visites:
                heapq.heappush(file, (cout + cout_arete, voisin, chemin + [voisin]))

    return [], float("inf"), explores


# ══════════════════════════════════════════════════════════════════════════════
# 6. AFFICHAGE
# ══════════════════════════════════════════════════════════════════════════════

def _afficher_log(logs: list[dict], racine: Noeud, n_iter: int) -> None:
    """Affiche les améliorations successives trouvées par MCTS."""
    print("\n  Progression de MCTS :")
    print(f"  {'Itération':>10} {'Coût':>6}  Chemin")
    print("  " + "-" * 40)
    for log in logs:
        print(f"  {log['iter']:>10} {log['cout']:>6}  {log['chemin']}")

    print(f"\n  Arbre construit ({_compter_noeuds(racine)} nœuds explorés / {n_iter} itérations)")
    print("\n  Statistiques UCB1 des enfants de la racine :")
    print(f"  {'Enfant':>8} {'Visites':>8} {'Récomp. moy':>12} {'UCB1':>10}")
    print("  " + "-" * 42)
    for enfant in sorted(racine.enfants, key=lambda n: n.visites, reverse=True):
        moy = enfant.recompense / max(1, enfant.visites)
        ucb = enfant.ucb1(math.sqrt(2))
        ucb_str = f"{ucb:.4f}" if not math.isinf(ucb) else "∞"
        print(f"  {enfant.etat:>8} {enfant.visites:>8} {moy:>12.4f} {ucb_str:>10}")


def _compter_noeuds(noeud: Noeud) -> int:
    return 1 + sum(_compter_noeuds(e) for e in noeud.enfants)


def afficher_graphe() -> None:
    """Affiche le graphe de façon lisible."""
    print("""
  Graphe (S = départ, G = objectif) :

       S
      / \\
    (1)  (4)
    /     \\
   A       B
  / \\       \\
(2) (5)    (1)
/     \\       \\
C      D       G ← OBJECTIF
 \\      \\
 (3)    (2)
   \\      \\
    G      G

  Tous les chemins :
    S → A → C → G  coût = 1+2+3 = 6
    S → A → D → G  coût = 1+5+2 = 8
    S → B → G      coût = 4+1   = 5  ← OPTIMAL
  """)


def afficher_comparaison(
    chemin_mcts: list[str], cout_mcts: int,
    chemin_dijk: list[str], cout_dijk: int, noeuds_dijk: int,
    noeuds_mcts: int,
) -> None:
    """Tableau comparatif MCTS vs Dijkstra."""
    sep = "═" * 58
    print(f"\n{sep}")
    print("  COMPARAISON MCTS vs DIJKSTRA")
    print(sep)
    print(f"  {'':25} {'MCTS':>12} {'Dijkstra':>12}")
    print("  " + "-" * 52)
    print(f"  {'Chemin trouvé':<25} {' → '.join(chemin_mcts):>12} {' → '.join(chemin_dijk):>12}")
    print(f"  {'Coût':<25} {cout_mcts:>12} {cout_dijk:>12}")
    print(f"  {'Nœuds explorés':<25} {noeuds_mcts:>12} {noeuds_dijk:>12}")
    print(f"  {'Optimal garanti ?':<25} {'Non':>12} {'Oui':>12}")
    print(f"  {'Scalable (grand espace) ?':<25} {'Oui ✓':>12} {'Non ✗':>12}")
    print(sep + "\n")

    if cout_mcts == cout_dijk:
        print("  ✓ MCTS a trouvé l'optimal cette fois.")
    else:
        diff = cout_mcts - cout_dijk
        print(f"  ~ MCTS a trouvé un chemin sous-optimal (+{diff} par rapport à Dijkstra).")
    print(f"    Dijkstra a dû explorer {noeuds_dijk} nœuds pour garantir l'optimal.")
    print(f"    MCTS n'en a exploré que {noeuds_mcts} (arbre construit en {n_iter_global} itérations).")
    print()


# ══════════════════════════════════════════════════════════════════════════════
# 7. DÉMONSTRATION VISUELLE ITÉRATION PAR ITÉRATION
# ══════════════════════════════════════════════════════════════════════════════

def demo_pas_a_pas(n_pas: int = 5) -> None:
    """
    Montre les n_pas premières itérations de MCTS en détail,
    pour expliquer chaque phase à l'oral.
    """
    random.seed(42)
    racine = Noeud(DEPART)

    print(f"\n{'─'*58}")
    print("  DÉMONSTRATION PAS À PAS (premières itérations)")
    print(f"{'─'*58}")

    for i in range(1, n_pas + 1):
        print(f"\n  ┌─ ITÉRATION {i} " + "─" * 40)

        # Phase 1
        noeud_sel = selectionner(racine, math.sqrt(2))
        print(f"  │ Phase 1 — Sélection  : nœud sélectionné = {noeud_sel.etat} "
              f"(visites={noeud_sel.visites})")

        # Phase 2
        if not noeud_sel.est_terminal() and not noeud_sel.est_completement_explore():
            noeud_exp = expansion(noeud_sel)
            print(f"  │ Phase 2 — Expansion  : nouveau nœud = {noeud_exp.etat} "
                  f"(coût cumulé={noeud_exp.cout_cumule})")
        else:
            noeud_exp = noeud_sel
            print(f"  │ Phase 2 — Expansion  : terminal ou complet, pas d'expansion")

        # Phase 3
        recompense = simulation(noeud_exp)
        print(f"  │ Phase 3 — Simulation : récompense = {recompense:.4f} "
              f"({'objectif atteint' if recompense > 0 else 'objectif non atteint'})")

        # Phase 4
        retropropagation(noeud_exp, recompense)
        print(f"  │ Phase 4 — Rétroprop. : statistiques mises à jour "
              f"(racine: visites={racine.visites})")
        print(f"  └" + "─" * 50)


# ══════════════════════════════════════════════════════════════════════════════
# 8. POINT D'ENTRÉE
# ══════════════════════════════════════════════════════════════════════════════

n_iter_global = 200  # accessible globalement pour l'affichage

if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════════════════╗
║         MCTS — Exemple pédagogique (graphe simple)      ║
║         Comparaison avec Dijkstra                       ║
╚══════════════════════════════════════════════════════════╝
    """)

    # Affiche le graphe
    afficher_graphe()

    # ── Démonstration pas à pas ──────────────────────────────────────────────
    demo_pas_a_pas(n_pas=6)

    # ── MCTS complet ─────────────────────────────────────────────────────────
    print("\n" + "=" * 58)
    print("  MCTS COMPLET (200 itérations, C = √2)")
    print("=" * 58)

    debut_mcts = time.perf_counter()
    chemin_mcts, cout_mcts = mcts(
        n_iterations = n_iter_global,
        C            = math.sqrt(2),
        verbose      = True,
        graine       = 42,
    )
    temps_mcts = (time.perf_counter() - debut_mcts) * 1000

    # Compter les nœuds explorés par MCTS (approximation = taille de l'arbre)
    racine_tmp = Noeud(DEPART)
    random.seed(42)
    for _ in range(n_iter_global):
        n = selectionner(racine_tmp, math.sqrt(2))
        if not n.est_terminal() and not n.est_completement_explore():
            n = expansion(n)
        r = simulation(n)
        retropropagation(n, r)
    noeuds_mcts = _compter_noeuds(racine_tmp)

    # ── Dijkstra ─────────────────────────────────────────────────────────────
    print("\n" + "=" * 58)
    print("  DIJKSTRA (référence)")
    print("=" * 58)

    debut_dijk = time.perf_counter()
    chemin_dijk, cout_dijk, noeuds_dijk = dijkstra()
    temps_dijk = (time.perf_counter() - debut_dijk) * 1000

    print(f"\n  Chemin optimal : {' → '.join(chemin_dijk)}")
    print(f"  Coût           : {cout_dijk}")
    print(f"  Nœuds explorés : {noeuds_dijk}")

    # ── Tableau comparatif ───────────────────────────────────────────────────
    afficher_comparaison(
        chemin_mcts, cout_mcts,
        chemin_dijk, cout_dijk, noeuds_dijk,
        noeuds_mcts,
    )

    # ── Message clé ─────────────────────────────────────────────────────────
    print("  POURQUOI MCTS EST MEILLEUR QUE DIJKSTRA POUR LE PROBLÈME SCORE ?")
    print("  " + "─" * 54)
    print("""
  Dijkstra garantit l'optimal MAIS :
    • Doit explorer tous les nœuds dans l'ordre des coûts
    • Complexité : O((V + E) log V) — explose quand V est grand
    • Dans SCORE : V = 4^59 configurations ≈ 10^35  (impossible)

  MCTS ne garantit PAS l'optimal MAIS :
    • Explore intelligemment via UCB1 (exploitation + exploration)
    • Converge vers de bonnes solutions sans tout explorer
    • Plus d'itérations = meilleure solution (anytime algorithm)
    • Scalable : fonctionne même quand l'espace est gigantesque

  → MCTS est donc l'approche naturelle pour le modèle SCORE
    où l'explosion combinatoire rend Dijkstra infaisable.
  """)
