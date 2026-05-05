"""
MCTS appliqué au modèle SCORE — Analyse de cyber-attaques sur véhicule autonome
================================================================================
Référence : Hutzler et al., "An autonomous vehicle in a connected environment:
            case study of cyber-resilience", FedCSIS 2024.

Modèle simplifié : chemin d'attaque IntHacker → DoorLock (Table III, cas 1a/1b/1c)
avec composants additionnels pour illustrer l'exploration MCTS.

Auteur  : stage IBISC
Date    : 2025
"""

from __future__ import annotations

import math
import random
import time
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Optional


# ══════════════════════════════════════════════════════════════════════════════
# 1. MODÈLE SCORE
# ══════════════════════════════════════════════════════════════════════════════

# Statuts possibles d'un composant logiciel (cf. papier §III)
STATUTS = ("F", "B", "M", "N")
# F = Functional (non compromis)
# B = Bad-data   (données corrompues, propagation limitée)
# M = Malware    (compromis, propagation maximale)
# N = Non-available (désactivé)


@dataclass(frozen=True)
class Transition:
    """
    Une transition dans le modèle SCORE.

    Correspond à une action unitaire de l'attaquant :
    compromettre le composant `vers` depuis le composant `depuis`
    au coût `cout`, en changeant son statut vers `statut_cible`.

    Pré-condition : le composant `depuis` doit être dans `statut_requis`.
    """
    depuis:        str   # composant source (attaquant)
    vers:          str   # composant cible
    cout:          int   # coût unitaire (inversement proportionnel à la vraisemblance)
    statut_cible:  str   # statut que prend `vers` après compromission
    statut_requis: str   # statut que doit avoir `depuis` pour déclencher


@dataclass
class EtatSysteme:
    """
    Configuration du système = vecteur de statuts de tous les composants.
    Équivalent à (q⃗, s⃗) dans la Définition 3.1 du papier.
    """
    statuts: dict[str, str]          # {composant: statut}
    cout_cumule: int = 0             # coût total accumulé depuis l'état initial
    historique: list[Transition] = field(default_factory=list)

    def copie(self) -> "EtatSysteme":
        return EtatSysteme(
            statuts=dict(self.statuts),
            cout_cumule=self.cout_cumule,
            historique=list(self.historique),
        )

    def appliquer(self, t: Transition) -> "EtatSysteme":
        """Retourne un nouvel état après application de la transition t."""
        nouvel_etat = self.copie()
        nouvel_etat.statuts[t.vers] = t.statut_cible
        nouvel_etat.cout_cumule += t.cout
        nouvel_etat.historique.append(t)
        return nouvel_etat

    def cle(self) -> str:
        """Clé unique représentant cet état (pour déduplication)."""
        return "|".join(f"{k}:{v}" for k, v in sorted(self.statuts.items()))

    def __repr__(self) -> str:
        compromis = {k: v for k, v in self.statuts.items() if v != "F"}
        return f"EtatSysteme(coût={self.cout_cumule}, compromis={compromis})"


class ModeleSCORE:
    """
    Encapsule le graphe de propagation SCORE :
    composants, transitions disponibles, objectif, coût acceptable.

    Petit modèle inspiré du cas d'étude véhicule autonome (Table III).
    Chemin principal : IntHacker → DuProxy → VehMonit → BodyDu → BodyMngt → DoorLock
    Chemin alternatif via BtHacker (coût plus élevé).
    """

    def __init__(self):
        # ── Composants du modèle ──────────────────────────────────────────────
        self.composants = [
            "IntHacker",   # attaquant Internet (entry point)
            "BtHacker",    # attaquant Bluetooth (entry point alternatif)
            "DuProxy",     # proxy de mise à jour
            "VehMonit",    # moniteur véhicule
            "BodyDu",      # body domain update
            "BodyMngt",    # gestion accès/démarrage véhicule  ← cible critique
            "DoorLock",    # verrouillage portes              ← objectif final
            "MmPlayer",    # lecteur multimédia (chemin Bt)
            "Navig",       # navigation
            "NavigPr",     # proxy navigation
            "AdasDec",     # décision ADAS
        ]

        # ── Transitions (depuis, vers, coût, statut_cible, statut_requis) ────
        # Source : Table III & IV du papier FedCSIS
        self.transitions: list[Transition] = [
            # ── Chemin 1a/1b : Internet → DoorLock (bad-data) ────────────────
            Transition("IntHacker", "DuProxy",  50, "B", "M"),
            Transition("DuProxy",   "VehMonit", 20, "B", "B"),
            Transition("VehMonit",  "BodyDu",    5, "B", "B"),
            Transition("BodyDu",    "BodyMngt",  20, "B", "B"),
            Transition("BodyMngt",  "DoorLock",   5, "B", "B"),

            # ── Chemin 1c : BodyDu → BodyMngt en malware (coût +10) ──────────
            Transition("BodyDu",    "BodyMngt",  30, "M", "B"),  # override B→M

            # ── Chemin 1e : Bluetooth → BodyMngt (coût élevé) ────────────────
            Transition("BtHacker",  "MmPlayer",  25, "M", "M"),
            Transition("MmPlayer",  "Navig",     10, "B", "M"),
            Transition("Navig",     "NavigPr",   20, "B", "B"),
            Transition("NavigPr",   "AdasDec",   15, "B", "B"),
            Transition("AdasDec",   "BodyMngt",  50, "B", "B"),

            # ── Chemin 2b : Internet → AdasDec (ADAS sabotage) ───────────────
            Transition("DuProxy",   "NavigPr",   20, "B", "B"),
            Transition("NavigPr",   "AdasDec",   15, "B", "B"),
        ]

        # ── Objectif de l'attaquant ───────────────────────────────────────────
        self.cible = "DoorLock"
        self.statuts_cibles = {"B", "M"}   # compromission partielle ou totale

        # ── Coût acceptable (seuil risque, cf. Table II) ──────────────────────
        self.cout_acceptable = 80

    def etat_initial(self, entry_point: str = "IntHacker") -> EtatSysteme:
        """Crée l'état initial : tous F sauf l'entry point en M."""
        statuts = {c: "F" for c in self.composants}
        statuts[entry_point] = "M"
        return EtatSysteme(statuts=statuts)

    def transitions_disponibles(self, etat: EtatSysteme) -> list[Transition]:
        """
        Retourne les transitions applicables dans l'état courant.
        Condition : composant source dans le bon statut ET cible encore F.
        """
        disponibles = []
        for t in self.transitions:
            if (etat.statuts.get(t.depuis) == t.statut_requis
                    and etat.statuts.get(t.vers) == "F"):
                disponibles.append(t)
        return disponibles

    def est_objectif(self, etat: EtatSysteme) -> bool:
        return etat.statuts.get(self.cible) in self.statuts_cibles

    def est_terminal(self, etat: EtatSysteme) -> bool:
        return self.est_objectif(etat) or len(self.transitions_disponibles(etat)) == 0


# ══════════════════════════════════════════════════════════════════════════════
# 2. MCTS
# ══════════════════════════════════════════════════════════════════════════════

class NoeudMCTS:
    """
    Nœud de l'arbre MCTS.

    Chaque nœud représente un état du système après une séquence d'actions.
    Les quatre phases classiques s'y appliquent :
      Sélection → Expansion → Simulation → Rétropropagation
    """

    def __init__(
        self,
        etat:    EtatSysteme,
        modele:  ModeleSCORE,
        parent:  Optional["NoeudMCTS"] = None,
        action:  Optional[Transition]  = None,
    ):
        self.etat   = etat
        self.modele = modele
        self.parent = parent
        self.action = action          # transition qui a mené à cet état

        self.enfants:     list["NoeudMCTS"] = []
        self.visites:     int   = 0
        self.recompense:  float = 0.0

        # Actions non encore explorées depuis cet état
        self._actions_non_explorees: list[Transition] = list(
            modele.transitions_disponibles(etat)
        )
        random.shuffle(self._actions_non_explorees)

    # ── Propriétés ─────────────────────────────────────────────────────────

    def est_completement_explore(self) -> bool:
        return len(self._actions_non_explorees) == 0

    def est_terminal(self) -> bool:
        return self.modele.est_terminal(self.etat)

    # ── UCB1 ───────────────────────────────────────────────────────────────

    def score_ucb1(self, C: float = math.sqrt(2)) -> float:
        """
        Upper Confidence Bound (UCB1) :
            UCB1 = (récompense moyenne) + C * sqrt(ln(visites_parent) / visites)

        Le terme d'exploitation favorise les nœuds avec une bonne récompense.
        Le terme d'exploration favorise les nœuds peu visités.
        C contrôle l'équilibre entre les deux.
        """
        if self.visites == 0:
            return float("inf")
        exploitation = self.recompense / self.visites
        exploration  = C * math.sqrt(math.log(self.parent.visites) / self.visites)
        return exploitation + exploration

    # ── Phases MCTS ────────────────────────────────────────────────────────

    def selectionner_enfant(self, C: float) -> "NoeudMCTS":
        """Phase 1 — Sélection : descend l'arbre par UCB1."""
        return max(self.enfants, key=lambda n: n.score_ucb1(C))

    def expansion(self) -> "NoeudMCTS":
        """
        Phase 2 — Expansion : crée un nœud enfant pour une action non explorée.
        """
        action = self._actions_non_explorees.pop()
        nouvel_etat = self.etat.appliquer(action)
        enfant = NoeudMCTS(nouvel_etat, self.modele, parent=self, action=action)
        self.enfants.append(enfant)
        return enfant

    def simulation(self, profondeur_max: int = 15) -> float:
        """
        Phase 3 — Simulation (rollout) : propagation aléatoire depuis cet état
        jusqu'à l'objectif ou blocage.

        Retourne une récompense normalisée dans [0, 1] :
          - 1.0  si objectif atteint à coût minimal
          - 0.0  si objectif non atteint
        """
        etat = self.etat.copie()
        profondeur = 0

        while not self.modele.est_terminal(etat) and profondeur < profondeur_max:
            actions = self.modele.transitions_disponibles(etat)
            if not actions:
                break
            # Politique de rollout : uniforme aléatoire
            # → peut être amélioré avec une heuristique (Q-learning, LCS...)
            action = random.choice(actions)
            etat = etat.appliquer(action)
            profondeur += 1

        if self.modele.est_objectif(etat):
            # Récompense inversement proportionnelle au coût (cf. approche ANSSI)
            return max(0.0, 1.0 - etat.cout_cumule / 300.0)
        return 0.0

    def retropropagation(self, recompense: float) -> None:
        """
        Phase 4 — Rétropropagation : remonte la récompense vers la racine.
        """
        noeud = self
        while noeud is not None:
            noeud.visites    += 1
            noeud.recompense += recompense
            noeud = noeud.parent

    def __repr__(self) -> str:
        action_str = f"{self.action.depuis}→{self.action.vers}" if self.action else "racine"
        return (f"Noeud({action_str}, "
                f"visites={self.visites}, "
                f"récompense_moy={self.recompense/max(1,self.visites):.3f})")


# ══════════════════════════════════════════════════════════════════════════════
# 3. ALGORITHME MCTS PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════

class MCTS:
    """
    Monte Carlo Tree Search pour la découverte automatique d'attaques SCORE.

    Chaque itération exécute les 4 phases :
      1. Sélection   — descend l'arbre en suivant UCB1
      2. Expansion   — explore une action non encore testée
      3. Simulation  — rollout aléatoire jusqu'à l'objectif
      4. Rétroprop.  — met à jour les statistiques remontant vers la racine

    En fin d'exécution, extrait le chemin de coût minimal trouvé.
    """

    def __init__(
        self,
        modele:        ModeleSCORE,
        C:             float = math.sqrt(2),
        graine:        int   = 42,
    ):
        self.modele = modele
        self.C      = C
        random.seed(graine)

    def recherche(
        self,
        etat_initial:   EtatSysteme,
        n_iterations:   int  = 500,
        verbose:        bool = True,
    ) -> tuple[list[Transition], int]:
        """
        Exécute MCTS depuis `etat_initial` pendant `n_iterations` itérations.

        Retourne :
          - chemin : liste de transitions du meilleur chemin trouvé
          - cout   : coût total du meilleur chemin
        """
        racine = NoeudMCTS(etat_initial, self.modele)
        meilleur_cout  = float("inf")
        meilleur_chemin: list[Transition] = []

        debut = time.time()

        for i in range(n_iterations):

            # ── Phase 1 : Sélection ─────────────────────────────────────────
            noeud = racine
            while (not noeud.est_terminal()
                   and noeud.est_completement_explore()
                   and noeud.enfants):
                noeud = noeud.selectionner_enfant(self.C)

            # ── Phase 2 : Expansion ─────────────────────────────────────────
            if not noeud.est_terminal() and not noeud.est_completement_explore():
                noeud = noeud.expansion()

            # ── Phase 3 : Simulation ────────────────────────────────────────
            recompense = noeud.simulation()

            # ── Phase 4 : Rétropropagation ──────────────────────────────────
            noeud.retropropagation(recompense)

            # ── Mise à jour du meilleur chemin si objectif atteint ──────────
            if self.modele.est_objectif(noeud.etat):
                cout = noeud.etat.cout_cumule
                if cout < meilleur_cout:
                    meilleur_cout   = cout
                    meilleur_chemin = list(noeud.etat.historique)
                    if verbose:
                        print(f"  [iter {i+1:4d}] Nouveau meilleur coût : {cout:3d}  "
                              f"chemin : {' → '.join(t.vers for t in meilleur_chemin)}")

        duree = time.time() - debut
        if verbose:
            print(f"\n  Recherche terminée en {duree:.3f}s ({n_iterations} itérations)")
            self._afficher_statistiques(racine)

        return meilleur_chemin, meilleur_cout

    # ── Affichage ───────────────────────────────────────────────────────────

    @staticmethod
    def _afficher_statistiques(racine: NoeudMCTS) -> None:
        """Affiche les statistiques des enfants directs de la racine."""
        print("\n  Statistiques des premiers mouvements :")
        print(f"  {'Action':<30} {'Visites':>8} {'Récomp. moy':>12} {'UCB1':>10}")
        print("  " + "-" * 62)
        for enfant in sorted(racine.enfants,
                             key=lambda n: n.recompense / max(1, n.visites),
                             reverse=True):
            action = f"{enfant.action.depuis}→{enfant.action.vers}({enfant.action.statut_cible})"
            moy    = enfant.recompense / max(1, enfant.visites)
            ucb    = enfant.score_ucb1(math.sqrt(2))
            print(f"  {action:<30} {enfant.visites:>8} {moy:>12.4f} "
                  f"{'inf' if math.isinf(ucb) else f'{ucb:.4f}':>10}")


# ══════════════════════════════════════════════════════════════════════════════
# 4. UTILITAIRES D'AFFICHAGE
# ══════════════════════════════════════════════════════════════════════════════

def afficher_chemin(chemin: list[Transition], cout: int, modele: ModeleSCORE) -> None:
    """Affiche le chemin d'attaque de manière lisible."""
    sep = "═" * 60
    print(f"\n{sep}")
    print("  MEILLEUR CHEMIN D'ATTAQUE TROUVÉ PAR MCTS")
    print(sep)

    if not chemin:
        print("  Aucun chemin vers l'objectif trouvé.")
        return

    cout_cumule = 0
    print(f"  {'Étape':<6} {'Depuis':<12} {'Vers':<12} {'Statut':>8} {'Coût':>6} {'Cumul':>6}")
    print("  " + "-" * 50)
    for i, t in enumerate(chemin, 1):
        cout_cumule += t.cout
        print(f"  {i:<6} {t.depuis:<12} {t.vers:<12} {t.statut_cible:>8} "
              f"{t.cout:>6} {cout_cumule:>6}")

    print("  " + "-" * 50)
    print(f"  Coût total           : {cout}")
    print(f"  Seuil acceptable     : {modele.cout_acceptable}")
    risque = "✗ RISQUE ÉLEVÉ" if cout <= modele.cout_acceptable else "✓ Risque acceptable"
    print(f"  Évaluation du risque : {risque}")
    print(sep + "\n")


def afficher_comparaison(resultats: dict) -> None:
    """Tableau comparatif multi-entrées."""
    print("\n" + "═" * 70)
    print("  COMPARAISON DES CHEMINS PAR POINT D'ENTRÉE")
    print("═" * 70)
    print(f"  {'Entry point':<14} {'Coût MCTS':>10} {'Coût papier':>12} {'Écart':>8} {'Chemin'}")
    print("  " + "-" * 66)
    for ep, (chemin, cout, cout_ref) in resultats.items():
        ecart = cout - cout_ref if cout_ref else "—"
        ecart_str = f"{ecart:+d}" if isinstance(ecart, int) else ecart
        path_str  = " → ".join(t.vers for t in chemin[:4])
        if len(chemin) > 4:
            path_str += " → ..."
        print(f"  {ep:<14} {cout:>10} {cout_ref:>12} {ecart_str:>8}   {path_str}")
    print("═" * 70 + "\n")


# ══════════════════════════════════════════════════════════════════════════════
# 5. EXPÉRIENCES
# ══════════════════════════════════════════════════════════════════════════════

def experience_principale():
    """
    Expérience 1 : MCTS depuis IntHacker (cas 1a du papier).
    Coût de référence : 100 (Table III).
    """
    print("\n" + "=" * 60)
    print("  EXPÉRIENCE 1 — Entry point : IntHacker")
    print("  Référence papier : coût = 100 (Table III, cas 1a)")
    print("=" * 60)

    modele      = ModeleSCORE()
    etat_init   = modele.etat_initial("IntHacker")
    mcts        = MCTS(modele, C=math.sqrt(2), graine=42)

    chemin, cout = mcts.recherche(etat_init, n_iterations=300, verbose=True)
    afficher_chemin(chemin, cout, modele)
    return chemin, cout


def experience_bluetooth():
    """
    Expérience 2 : MCTS depuis BtHacker (cas 1e du papier).
    Coût de référence : 120 (Table III).
    """
    print("\n" + "=" * 60)
    print("  EXPÉRIENCE 2 — Entry point : BtHacker")
    print("  Référence papier : coût = 120 (Table III, cas 1e)")
    print("=" * 60)

    modele      = ModeleSCORE()
    etat_init   = modele.etat_initial("BtHacker")
    mcts        = MCTS(modele, C=math.sqrt(2), graine=0)

    chemin, cout = mcts.recherche(etat_init, n_iterations=300, verbose=True)
    afficher_chemin(chemin, cout, modele)
    return chemin, cout


def experience_sensibilite_C():
    """
    Expérience 3 : sensibilité au paramètre d'exploration C (UCB1).
    Montre l'impact de C sur la qualité de la solution et le nb d'itérations.
    """
    print("\n" + "=" * 60)
    print("  EXPÉRIENCE 3 — Sensibilité au paramètre C (UCB1)")
    print("=" * 60)

    modele    = ModeleSCORE()
    etat_init = modele.etat_initial("IntHacker")

    print(f"\n  {'C':>6} {'Coût trouvé':>12} {'Coût réf.':>10} {'Temps (ms)':>12}")
    print("  " + "-" * 44)

    for C in [0.5, 1.0, math.sqrt(2), 2.0, 3.0]:
        debut   = time.time()
        mcts    = MCTS(modele, C=C, graine=42)
        _, cout = mcts.recherche(etat_init, n_iterations=200, verbose=False)
        duree   = (time.time() - debut) * 1000
        cout_str = str(cout) if cout < float("inf") else "non trouvé"
        print(f"  {C:>6.2f} {cout_str:>12} {'100':>10} {duree:>11.1f}ms")


def experience_iterations():
    """
    Expérience 4 : convergence MCTS selon le nombre d'itérations.
    Illustre l'amélioration progressive de la solution.
    """
    print("\n" + "=" * 60)
    print("  EXPÉRIENCE 4 — Convergence selon nb d'itérations")
    print("=" * 60)

    modele    = ModeleSCORE()
    etat_init = modele.etat_initial("IntHacker")

    print(f"\n  {'Itérations':>12} {'Meilleur coût':>14} {'Trouvé ?':>10}")
    print("  " + "-" * 40)

    for n_iter in [10, 25, 50, 100, 200, 500]:
        mcts    = MCTS(modele, C=math.sqrt(2), graine=42)
        _, cout = mcts.recherche(etat_init, n_iterations=n_iter, verbose=False)
        trouve  = "✓" if cout < float("inf") else "✗"
        cout_str = str(cout) if cout < float("inf") else "—"
        print(f"  {n_iter:>12} {cout_str:>14} {trouve:>10}")


# ══════════════════════════════════════════════════════════════════════════════
# 6. POINT D'ENTRÉE
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════════════════════╗
║   MCTS pour l'analyse de cyber-attaques — Modèle SCORE      ║
║   Basé sur Hutzler et al., FedCSIS 2024                     ║
╚══════════════════════════════════════════════════════════════╝
    """)

    # Expérience principale (cas 1a du papier)
    chemin_int, cout_int = experience_principale()

    # Expérience Bluetooth (cas 1e du papier)
    chemin_bt, cout_bt = experience_bluetooth()

    # Comparaison avec les coûts du papier
    afficher_comparaison({
        "IntHacker": (chemin_int, cout_int, 100),
        "BtHacker":  (chemin_bt,  cout_bt,  120),
    })

    # Analyses de sensibilité
    experience_sensibilite_C()
    experience_iterations()

    print("\n[Fin des expériences]\n")
