"""
MCTS branché sur le vrai simulateur SCORE
==========================================
Fichier : mcts_score_real.py

Ce fichier implémente MCTS en s'appuyant directement sur les classes
du simulateur SCORE fourni par le laboratoire IBISC :
  - Automata  (automata.py)   : le moteur de simulation
  - Model     (model.py)      : structure du modèle JSON
  - batchInit (batchInit.py)  : chargement état initial / cible

Interface avec le simulateur :
  netAutomata.next(maxCost)    → liste des ActiveTransition disponibles
  netAutomata.do(transition)   → applique une transition
  netAutomata.reset(loc, secr) → remet à l'état initial

Usage :
  python mcts_score_real.py
  (place small_vehicle.json et small_vehicle.start dans ./jsons/)

Référence :
  Hutzler et al., "An autonomous vehicle in a connected environment:
  case study of cyber-resilience", FedCSIS 2024.
"""

from __future__ import annotations

import json
import math
import random
import time
import sys
import copy
from typing import Optional

# ── Imports du simulateur SCORE ──────────────────────────────────────────────
from model import Model
from automata import Automata
from automaton import ActiveTransition, Location, Actions, Trans, SetSecr
from batchInit import InitBatch
from interActiveInit import InteractiveInit


# ══════════════════════════════════════════════════════════════════════════════
# 1. ÉTAT MCTS — SNAPSHOT DE L'ÉTAT DU SIMULATEUR
# ══════════════════════════════════════════════════════════════════════════════

class SnapshotEtat:
    """
    Capture l'état complet du simulateur à un instant donné.
    Permet de sauvegarder / restaurer l'état pour les simulations MCTS.

    Le simulateur SCORE travaille avec des références mutables
    (currentLoc, currentSecr, currentCost) — on doit donc faire
    des copies explicites pour chaque nœud de l'arbre MCTS.
    """

    def __init__(self, automata: Automata):
        # Copie profonde des listes mutables du simulateur
        self.locations: list[Location] = list(automata.currentLoc)
        self.secrets:   list[bool]     = list(automata.currentSecr)
        self.cout:      int            = automata.currentCost

    def restaurer(self, automata: Automata) -> None:
        """Remet le simulateur dans l'état capturé."""
        automata.reset(self.locations, self.secrets)
        automata.currentCost = self.cout

    def __repr__(self) -> str:
        locs = [loc.name for loc in self.locations]
        return f"Snapshot(coût={self.cout}, locs={locs})"


# ══════════════════════════════════════════════════════════════════════════════
# 2. NŒUD MCTS
# ══════════════════════════════════════════════════════════════════════════════

class NoeudMCTS:
    """
    Nœud de l'arbre MCTS.

    Chaque nœud correspond à un état du simulateur SCORE atteint après
    une séquence de transitions. Il porte :
      - un snapshot de l'état (pour restauration)
      - la transition qui y a mené (ActiveTransition du simulateur)
      - les statistiques UCB1 (visites, récompense)
      - la liste des transitions non encore explorées
    """

    def __init__(
        self,
        snapshot:    SnapshotEtat,
        automata:    Automata,
        finalState:  Actions,
        maxCost:     int,
        parent:      Optional["NoeudMCTS"]      = None,
        transition:  Optional[ActiveTransition] = None,
    ):
        self.snapshot    = snapshot
        self.parent      = parent
        self.transition  = transition    # ActiveTransition qui a mené ici (None pour la racine)

        self.visites:    int   = 0
        self.recompense: float = 0.0
        self.enfants:    list["NoeudMCTS"] = []

        # Actions disponibles depuis cet état — obtenues via le simulateur
        # On restaure d'abord l'état, puis on appelle next()
        snapshot.restaurer(automata)
        self._transitions_disponibles: list[ActiveTransition] = list(
            automata.next(maxCost)
        )
        random.shuffle(self._transitions_disponibles)

        # Vérifier si l'objectif est déjà atteint dans cet état
        self._est_terminal: bool = _verifier_objectif(automata, finalState)
        if not self._est_terminal and len(self._transitions_disponibles) == 0:
            self._est_terminal = True  # impasse (deadlock)

    # ── Propriétés ──────────────────────────────────────────────────────────

    def est_terminal(self) -> bool:
        return self._est_terminal

    def est_completement_explore(self) -> bool:
        return len(self._transitions_disponibles) == 0

    # ── UCB1 ────────────────────────────────────────────────────────────────

    def ucb1(self, C: float) -> float:
        """
        UCB1 = recompense/visites + C * sqrt(ln(visites_parent) / visites)

        Adaptation SCORE :
          - récompense = 1 - coût_total / (maxCost * 2)
          - coût faible → récompense haute → nœud préféré (approche ANSSI)
        """
        if self.visites == 0:
            return float("inf")
        exploitation = self.recompense / self.visites
        exploration  = C * math.sqrt(math.log(self.parent.visites) / self.visites)
        return exploitation + exploration

    def __repr__(self) -> str:
        nom = self.transition.name if self.transition else "racine"
        moy = self.recompense / self.visites if self.visites > 0 else 0.0
        return f"Noeud({nom}, v={self.visites}, r={moy:.3f}, coût={self.snapshot.cout})"


# ══════════════════════════════════════════════════════════════════════════════
# 3. FONCTIONS UTILITAIRES
# ══════════════════════════════════════════════════════════════════════════════

def _verifier_objectif(automata: Automata, finalState: Actions) -> bool:
    """
    Vérifie si l'état courant du simulateur satisfait l'objectif.
    Reprise directe de la fonction done() de system.py / dqnScore.py.
    """
    for trans in finalState.transitions:
        if automata.currentLoc[trans.softComp] != trans.location:
            return False
    for secret in finalState.secretChange:
        if secret.val != automata.currentSecr[secret.secr]:
            return False
    return True


def _recompense(cout_total: int, max_cout: int) -> float:
    """
    Récompense inversement proportionnelle au coût (approche ANSSI).
    Normalisée dans [0, 1].
    """
    return max(0.0, 1.0 - cout_total / (max_cout * 2.0))


# ══════════════════════════════════════════════════════════════════════════════
# 4. LES 4 PHASES MCTS
# ══════════════════════════════════════════════════════════════════════════════

def selectionner(racine: NoeudMCTS, C: float) -> NoeudMCTS:
    """
    Phase 1 — Sélection
    Descend l'arbre en suivant UCB1 jusqu'à trouver un nœud
    non complètement exploré ou terminal.
    """
    noeud = racine
    while (not noeud.est_terminal()
           and noeud.est_completement_explore()
           and noeud.enfants):
        noeud = max(noeud.enfants, key=lambda n: n.ucb1(C))
    return noeud


def expansion(
    noeud:       NoeudMCTS,
    automata:    Automata,
    finalState:  Actions,
    maxCost:     int,
) -> NoeudMCTS:
    """
    Phase 2 — Expansion
    Applique une transition non encore explorée via le simulateur,
    capture l'état résultant dans un nouveau nœud fils.
    """
    # Restaurer l'état du nœud parent dans le simulateur
    noeud.snapshot.restaurer(automata)

    # Choisir une transition non encore essayée
    transition = noeud._transitions_disponibles.pop()

    # Appliquer la transition dans le simulateur
    automata.do(transition)

    # Capturer le nouvel état
    nouveau_snapshot = SnapshotEtat(automata)

    # Créer le nœud fils
    enfant = NoeudMCTS(
        snapshot   = nouveau_snapshot,
        automata   = automata,
        finalState = finalState,
        maxCost    = maxCost,
        parent     = noeud,
        transition = transition,
    )
    noeud.enfants.append(enfant)
    return enfant


def simulation(
    noeud:       NoeudMCTS,
    automata:    Automata,
    finalState:  Actions,
    maxCost:     int,
    profMax:     int = 15,
) -> float:
    """
    Phase 3 — Simulation (rollout)
    Depuis le nœud courant, joue aléatoirement via le simulateur
    jusqu'à l'objectif, le deadlock, ou la profondeur maximale.
    Ne modifie PAS l'arbre MCTS.

    Politique : uniforme aléatoire (peut être améliorée avec LCS/Q-learning).
    """
    # Restaurer l'état du nœud dans le simulateur
    noeud.snapshot.restaurer(automata)

    profondeur = 0
    while profondeur < profMax:
        # Vérifier si l'objectif est atteint
        if _verifier_objectif(automata, finalState):
            return _recompense(automata.currentCost, maxCost)

        # Récupérer les transitions disponibles
        disponibles = automata.next(maxCost)
        if not disponibles:
            break  # deadlock

        # Politique aléatoire uniforme
        action = random.choice(disponibles)
        automata.do(action)
        profondeur += 1

    # Vérification finale
    if _verifier_objectif(automata, finalState):
        return _recompense(automata.currentCost, maxCost)
    return 0.0


def retropropagation(noeud: NoeudMCTS, recompense: float) -> None:
    """
    Phase 4 — Rétropropagation
    Remonte la récompense vers la racine.
    """
    curseur = noeud
    while curseur is not None:
        curseur.visites    += 1
        curseur.recompense += recompense
        curseur = curseur.parent


# ══════════════════════════════════════════════════════════════════════════════
# 5. ALGORITHME MCTS PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════

class MCTSScore:
    """
    MCTS branché sur le simulateur SCORE.

    Utilise directement :
      - Automata.next(maxCost) pour obtenir les transitions disponibles
      - Automata.do(transition) pour appliquer une transition
      - Automata.reset(loc, secr) pour restaurer un état via SnapshotEtat
    """

    def __init__(
        self,
        automata:   Automata,
        finalState: Actions,
        maxCost:    int,
        C:          float = math.sqrt(2),
        graine:     int   = 42,
    ):
        self.automata   = automata
        self.finalState = finalState
        self.maxCost    = maxCost
        self.C          = C
        random.seed(graine)

    def recherche(
        self,
        n_iterations: int  = 500,
        profMax:      int  = 15,
        verbose:      bool = True,
    ) -> tuple[list[ActiveTransition], int]:
        """
        Lance la recherche MCTS.

        Retourne :
          - chemin : liste d'ActiveTransition (transitions du simulateur)
          - cout   : coût total du meilleur chemin trouvé
        """
        # Capturer l'état initial
        snapshot_initial = SnapshotEtat(self.automata)
        racine = NoeudMCTS(
            snapshot   = snapshot_initial,
            automata   = self.automata,
            finalState = self.finalState,
            maxCost    = self.maxCost,
        )

        meilleur_cout   = float("inf")
        meilleur_chemin: list[ActiveTransition] = []
        debut = time.perf_counter()

        for i in range(1, n_iterations + 1):

            # ── Phase 1 : Sélection ─────────────────────────────────────────
            noeud = selectionner(racine, self.C)

            # ── Phase 2 : Expansion ─────────────────────────────────────────
            if not noeud.est_terminal() and not noeud.est_completement_explore():
                noeud = expansion(noeud, self.automata, self.finalState, self.maxCost)

            # ── Phase 3 : Simulation ────────────────────────────────────────
            recompense = simulation(
                noeud, self.automata, self.finalState, self.maxCost, profMax
            )

            # ── Phase 4 : Rétropropagation ──────────────────────────────────
            retropropagation(noeud, recompense)

            # ── Mise à jour du meilleur chemin ──────────────────────────────
            # Restaurer l'état du nœud pour vérifier si c'est l'objectif
            noeud.snapshot.restaurer(self.automata)
            if _verifier_objectif(self.automata, self.finalState):
                cout = self.automata.currentCost
                if cout < meilleur_cout:
                    meilleur_cout = cout
                    # Reconstituer le chemin depuis la racine
                    chemin = []
                    cur = noeud
                    while cur.transition is not None:
                        chemin.append(cur.transition)
                        cur = cur.parent
                    meilleur_chemin = list(reversed(chemin))
                    if verbose:
                        print(f"  [iter {i:4d}] Nouveau meilleur coût : {cout:3d} | "
                              f"chemin : {' → '.join(t.name for t in meilleur_chemin)}")

        # Restaurer l'état initial à la fin
        snapshot_initial.restaurer(self.automata)

        duree = (time.perf_counter() - debut) * 1000
        if verbose:
            print(f"\n  Recherche terminée en {duree:.1f}ms ({n_iterations} itérations)")
            self._afficher_stats(racine)

        return meilleur_chemin, meilleur_cout

    def _afficher_stats(self, racine: NoeudMCTS) -> None:
        """Affiche les statistiques UCB1 des enfants de la racine."""
        if not racine.enfants:
            print("  Aucun enfant exploré.")
            return
        print(f"\n  {'Action':<45} {'Visites':>8} {'Récomp.moy':>11} {'UCB1':>10}")
        print("  " + "-" * 78)
        for enfant in sorted(racine.enfants,
                             key=lambda n: n.recompense / max(1, n.visites),
                             reverse=True):
            moy = enfant.recompense / max(1, enfant.visites)
            ucb = enfant.ucb1(self.C)
            ucb_s = f"{ucb:.4f}" if not math.isinf(ucb) else "∞"
            print(f"  {str(enfant.transition):<45} {enfant.visites:>8} "
                  f"{moy:>11.4f} {ucb_s:>10}")


# ══════════════════════════════════════════════════════════════════════════════
# 6. AFFICHAGE DU RÉSULTAT
# ══════════════════════════════════════════════════════════════════════════════

def afficher_resultat(
    chemin:     list[ActiveTransition],
    cout:       int,
    maxCost:    int,
    automata:   Automata,
    finalState: Actions,
) -> None:
    """Affiche le chemin d'attaque trouvé par MCTS de façon lisible."""
    sep = "═" * 65
    print(f"\n{sep}")
    print("  MEILLEUR CHEMIN D'ATTAQUE TROUVÉ PAR MCTS")
    print(sep)

    if not chemin:
        print("  Aucun chemin vers l'objectif trouvé.")
        print(sep)
        return

    print(f"\n  {'Étape':<6} {'Composant':<20} {'Transition':<25} {'Coût':>6} {'Cumul':>7}")
    print("  " + "-" * 66)

    cout_cumule = 0
    for i, t in enumerate(chemin, 1):
        cout_cumule += t.cost
        node_name = automata.model.nodes[t.nodeIndex].name if t.nodeIndex >= 0 else "—"
        print(f"  {i:<6} {node_name:<20} {t.name:<25} {t.cost:>6} {cout_cumule:>7}")

    print("  " + "-" * 66)
    print(f"  Coût total        : {cout}")
    print(f"  Coût acceptable   : {maxCost}")
    risque = "✗  RISQUE ÉLEVÉ — protection insuffisante" if cout <= maxCost else "✓  Risque acceptable"
    print(f"  Évaluation risque : {risque}")
    print(sep + "\n")


# ══════════════════════════════════════════════════════════════════════════════
# 7. SENSIBILITÉ AU PARAMÈTRE C
# ══════════════════════════════════════════════════════════════════════════════

def experience_sensibilite_C(
    system:      Model,
    initialLoc:  list,
    initialtSecr: list,
    finalState:  Actions,
    maxCost:     int,
    n_iter:      int = 300,
) -> None:
    """
    Montre l'impact du paramètre C sur la qualité de la solution.
    Utile pour justifier le choix C = √2 devant les encadrants.
    """
    print("\n" + "=" * 55)
    print("  SENSIBILITÉ AU PARAMÈTRE C (UCB1)")
    print("=" * 55)
    print(f"  {'C':>6} {'Coût trouvé':>12} {'Temps (ms)':>12} {'Trouvé':>8}")
    print("  " + "-" * 42)

    for C_val in [0.5, 1.0, math.sqrt(2), 2.0, 3.0]:
        automata = Automata(system, initialLoc, initialtSecr)
        mcts = MCTSScore(automata, finalState, maxCost, C=C_val, graine=42)
        debut = time.perf_counter()
        _, cout = mcts.recherche(n_iterations=n_iter, verbose=False)
        duree = (time.perf_counter() - debut) * 1000
        cout_s  = str(cout) if cout < float("inf") else "non trouvé"
        trouve  = "✓" if cout < float("inf") else "✗"
        print(f"  {C_val:>6.2f} {cout_s:>12} {duree:>11.1f}ms {trouve:>8}")


# ══════════════════════════════════════════════════════════════════════════════
# 8. POINT D'ENTRÉE
# ══════════════════════════════════════════════════════════════════════════════

def main() -> int:
    print("""
╔══════════════════════════════════════════════════════════════╗
║   MCTS branché sur le simulateur SCORE — IBISC / SystemX    ║
║   Modèle : small_vehicle  (IntHacker → DoorLock)            ║
╚══════════════════════════════════════════════════════════════╝
    """)

    # ── Chargement du modèle JSON ────────────────────────────────────────────
    # Place small_vehicle.json et small_vehicle.start dans ./jsons/
    systemPath = "./jsons/small_vehicle.json"

    print(f"Chargement du modèle : {systemPath}")
    with open(systemPath, "r") as f:
        data = json.load(f)
    system: Model = Model(**data)

    print(f"Modèle chargé : {system.nbNodes} nœuds, {system.nbSecrets} secrets\n")

    # ── Chargement état initial / cible ─────────────────────────────────────
    batchFilePath = systemPath.replace(".json", ".start")
    initBatch = InitBatch(batchFilePath, system)

    if initBatch.cr != 0:
        print("Fichier .start introuvable, initialisation interactive...")
        interInit = InteractiveInit(system)
        initialLoc   = interInit.initLocality()
        initialtSecr = interInit.initSecrets()
        finalState   = interInit.initTarget()
    else:
        initialLoc   = initBatch.initialLoc
        initialtSecr = initBatch.initialtSecr
        finalState   = initBatch.finalState
        print("Initialisation batch :")
        print(initBatch)

    # ── Instanciation du simulateur ──────────────────────────────────────────
    maxCost = 110   # seuil de coût acceptable (feared event 1, Table II FedCSIS)

    automata = Automata(system, initialLoc, initialtSecr)

    print(f"État initial du simulateur :")
    for i in range(automata.nbNodes):
        print(f"  {automata.model.nodes[i].name:<15} → {automata.currentLoc[i].name}")

    # ── MCTS principal ───────────────────────────────────────────────────────
    print("\n" + "=" * 55)
    print(f"  MCTS — {500} itérations, C = √2 ≈ {math.sqrt(2):.3f}")
    print("=" * 55 + "\n")

    mcts = MCTSScore(
        automata   = automata,
        finalState = finalState,
        maxCost    = maxCost,
        C          = math.sqrt(2),
        graine     = 42,
    )

    chemin, cout = mcts.recherche(n_iterations=500, profMax=15, verbose=True)

    # Afficher le résultat
    afficher_resultat(chemin, cout, maxCost, automata, finalState)

    # ── Vérification : rejouer le chemin dans le simulateur ──────────────────
    if chemin:
        print("  Vérification — rejeu du chemin dans le simulateur :")
        automata.reset(initialLoc, initialtSecr)
        for t in chemin:
            automata.do(t)
        ok = _verifier_objectif(automata, finalState)
        print(f"  Objectif atteint après rejeu : {'✓ OUI' if ok else '✗ NON'}")
        print(f"  Coût total simulateur        : {automata.currentCost}\n")

    # ── Analyse de sensibilité au paramètre C ────────────────────────────────
    experience_sensibilite_C(
        system, initialLoc, initialtSecr, finalState, maxCost, n_iter=300
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
