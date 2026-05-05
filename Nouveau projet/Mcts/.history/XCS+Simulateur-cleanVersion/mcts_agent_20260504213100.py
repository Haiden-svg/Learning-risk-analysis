import random
import math
from typing import Optional
from automaton import ActiveTransition # On importe ActiveTransition pour le typage

# --- Classe pour représenter un nœud de l'arbre MCTS ---
class MCTSNode:
    def __init__(self, state_loc, state_secr, current_cost, parent=None, action=None):
        # L'état de la voiture à ce nœud (Location des noeuds et état des secrets)
        self.state_loc = state_loc.copy()
        self.state_secr = state_secr.copy()
        self.current_cost = current_cost
        
        # Structure de l'arbre
        self.parent = parent
        self.action = action  # L'action (ActiveTransition) qui a mené de parent -> ce noeud
        self.children = []
        
        # Liste des actions possibles depuis cet état
        # (Sera remplie lors de la création du noeud ou lors de son expansion)
        self.untried_actions = [] 
        
        # Statistiques MCTS
        self.visits = 0
        # Score cumulé (réussite des simulations passant par ce noeud)
        self.score = 0.0 
        
    def is_fully_expanded(self):
        # Un nœud est complètement exploré s'il a des enfants ET plus aucune action non tentée
        return len(self.untried_actions) == 0 and len(self.children) > 0


# --- Classe Principale de l'Agent MCTS ---
class MCTSAgent:
    def __init__(self, env, maxCost, num_iterations=1000, exploration_constant=1.41):
        self.env = env
        self.maxCost = maxCost
        self.num_iterations = num_iterations
        # La constante C gère le compromis entre creuser un bon chemin (exploitation) 
        # et essayer de nouveaux chemins (exploration). 1.41 (sqrt(2)) est la norme mathématique.
        self.exploration_constant = exploration_constant

    def selectAction(self, maxCost, step, stat=False) -> Optional[ActiveTransition]:
        """
        Point d'entrée principal. Le simulateur demande "Quelle est la meilleure action maintenant ?"
        Le MCTS va faire ses simulations mentales et répondre.
        """
        print(f"\n[MCTS] Démarrage de la réflexion pour l'étape {step} (Coût actuel : {self.env.automata.currentCost})")
        
        # 1. Sauvegarder l'état "réel" actuel de l'automate
        root_loc = self.env.automata.currentLoc.copy()
        root_secr = self.env.automata.currentSecr.copy()
        root_cost = self.env.automata.currentCost
        
        # 2. Créer le nœud racine
        root_node = MCTSNode(root_loc, root_secr, root_cost)
        
        # Initialiser les actions non tentées de la racine
        self.env.resetState(root_loc, root_secr)
        self.env.automata.currentCost = root_cost
        root_node.untried_actions = self.env.automata.next(maxCost)
        
        if not root_node.untried_actions:
            print("[MCTS] Plus aucune action possible (Deadlock).")
            return None 
            
        # 3. Boucle principale du MCTS
        for i in range(self.num_iterations):
            node = root_node
            
            # --- Préparation : on remet l'environnement mental à l'état de la racine ---
            self.env.resetState(root_loc, root_secr)
            self.env.automata.currentCost = root_cost

            # --- PHASE 1 : SÉLECTION ---
            # Tant que le nœud est "fini" et qu'on n'a pas atteint le but
            while node.is_fully_expanded() and not self.env.done():
                node = self._select_best_child_uct(node)
                # On joue le coup mentalement
                self.env.automata.do(node.action)

            # --- PHASE 2 : EXPANSION ---
            if node.untried_actions and not self.env.done():
                # On choisit une action au hasard parmi celles qu'on n'a pas encore essayées
                action = random.choice(node.untried_actions)
                node.untried_actions.remove(action)
                
                # On joue cette action mentalement
                self.env.automata.do(action)
                
                # On crée le nœud enfant
                new_state_loc = self.env.automata.currentLoc.copy()
                new_state_secr = self.env.automata.currentSecr.copy()
                new_cost = self.env.automata.currentCost
                
                child_node = MCTSNode(new_state_loc, new_state_secr, new_cost, parent=node, action=action)
                
                # On récupère les actions possibles depuis ce nouvel état
                child_node.untried_actions = self.env.automata.next(maxCost)
                
                node.children.append(child_node)
                node = child_node # On se place sur l'enfant pour la suite

            # --- PHASE 3 : SIMULATION (Playout) ---
            reward = self._simulate(maxCost)
            
            # --- PHASE 4 : RÉTROPROPAGATION ---
            self._backpropagate(node, reward)

        # 4. Choix final
        # On restaure l'état "réel" de la voiture une dernière fois
        self.env.resetState(root_loc, root_secr)
        self.env.automata.currentCost = root_cost
        
        # Le "Robust Child" : le nœud enfant de la racine qui a été visité le plus souvent
        best_child = max(root_node.children, key=lambda c: c.visits)
        
        print(f"[MCTS] Action choisie : {best_child.action.name} (Visites : {best_child.visits}/{self.num_iterations})")
        return best_child.action

    # --- Méthodes Internes ---

    def _select_best_child_uct(self, node: MCTSNode) -> MCTSNode:
        """
        Phase de Sélection : Algorithme UCB1
        Cherche le meilleur ratio (Victoire/Visite) + Bonus d'exploration
        """
        best_score = float('-inf')
        best_child = None
        
        for child in node.children:
            if child.visits == 0:
                return child # On force l'exploration des noeuds non visités
            
            exploitation = child.score / child.visits
            exploration = self.exploration_constant * math.sqrt(math.log(node.visits) / child.visits)
            uct_value = exploitation + exploration
            
            if uct_value > best_score:
                best_score = uct_value
                best_child = child
                
        return best_child

    def _simulate(self, maxCost) -> float:
        """
        Phase de Simulation : Joue des coups totalement au hasard (Playout) 
        jusqu'à la victoire, un deadlock, ou la limite budgétaire.
        """
        # Limite de sécurité pour éviter une boucle infinie de petites actions 
        # qui ne coûtent rien
        max_sim_steps = 30 
        steps = 0
        
        while not self.env.done() and steps < max_sim_steps:
            possible_actions = self.env.automata.next(maxCost)
            if not possible_actions:
                break # On est bloqué (Deadlock)
            
            # Joue au hasard
            action = random.choice(possible_actions)
            self.env.automata.do(action)
            steps += 1
            
        # --- CALCUL DE LA RÉCOMPENSE ---
        if self.env.done():
            # Si on a gagné, on donne un score de 1.
            # BONUS : On peut rajouter une petite fraction pour récompenser les attaques moins chères
            # Exemple : 1.0 + (budget restant / budget max)
            cost_ratio = max(0, (maxCost - self.env.automata.currentCost) / maxCost)
            return 1.0 + cost_ratio
        else:
            # L'attaque a échoué (Deadlock ou limite de coups atteinte sans atteindre la cible)
            return 0.0

    def _backpropagate(self, node: MCTSNode, reward: float):
        """
        Phase de Rétropropagation : Remonte jusqu'à la racine pour mettre à jour
        les statistiques (Visites et Score)
        """
        while node is not None:
            node.visits += 1
            node.score += reward
            node = node.parent