from xcs.bitstrings import BitString
from xcs.scenarios import Scenario
from automaton import Location


# === Définir la classe Scenario pour XCS ===
class CarHackScenario(Scenario):
    def __init__(self, automata, init_loc, init_secr, targets, target_state, max_cost, max_step):
        self.automata = automata
        self.init_loc = init_loc
        self.init_secr = init_secr
        self.target_index = targets
        self.target_state = target_state
        self.max_cost = max_cost
        self.max_steps = max_step
        self.current_step = 0
        self.searching = True
        self.action_encoder = {}  # (name, module_index) → id
        self.action_decoder = {}  # id → transition
        self.trace = []
        self.global_transitions = self.get_all_transitions()
        self.initialize_action_encodings()

    def get_all_transitions(self):
        all_transitions = []
        for template in self.automata.nodes:
            for loc in template.automaton:
                all_transitions.extend(template.automaton[loc])

        for node in self.automata.model.nodes:
            print(node.name, end=", ")
        print("\nNb de transitions :", len(all_transitions), "\n Nb de modules :", len(self.automata.model.nodes))
        return all_transitions

    def build_transition_key(self, t):
        return (
            t.name,
            t.transIndex,
            tuple(sorted(
                (tr.softComp, tr.location.name)
                for tr in t.update.transitions
            )
            )
        )

    def initialize_action_encodings(self):
        for t in self.global_transitions:
            key = self.build_transition_key(t)
            if key not in self.action_encoder:
                new_id = len(self.action_encoder)
                self.action_encoder[key] = new_id
                self.action_decoder[new_id] = t
        # print(len(self.action_encoder), len(self.action_decoder))

    def reset(self):
        self.automata.reset(self.init_loc, self.init_secr)
        self.current_step = 0
        self.trace = []
        self.searching = True
        return self.sense()

    # elle récupere l'etat de tout les modules
    def sense(self):
        # encodage de l'état des modules en 2 bits
        mapping = {
            Location.FUNC: [0, 0],
            Location.MALW: [0, 1],
            Location.BADD: [1, 0],
            Location.NOAV: [1, 1]
        }

        bits = []

        for i in range(len(self.automata.currentLoc)):
            loc = self.automata.currentLoc[i]
            bits.extend(mapping.get(loc, [0, 0]))

        return BitString(''.join(str(bit) for bit in bits))

    def get_possible_actions(self):
        # retourne toutes les transitions du modèl, sans exception (fonction appelée par XCS automatiquement)
        return list(self.action_decoder.keys())

    def find_equivalent_in_next(self, transition_global):
        """À partir d'une transition globale, retrouve son équivalent enrichi dans automata.next()."""
        key = self.build_transition_key(transition_global)

        for t_next in self.automata.next(self.max_cost):
            if self.build_transition_key(t_next) == key:
                # print(transition_global, "\n", t_next)
                return t_next  # Transition faisable au format enrichi

        return None  # pas faisable actuellement

    def execute(self, action_id):
        # Récupérer la transition associée à cet ID
        transition = self.action_decoder.get(action_id)

        # Rechercher son équivalent dans les transitions actuellement faisables (format build key)
        transition_key = self.find_equivalent_in_next(transition)

        if transition_key is None:
            return -20  # pénalité pour action non faisable

        # print("transition effectuée :", transition_key, transition_key.cost, end=" / ")
        self.automata.do(transition_key)
        self.current_step += 1
        self.trace.append(transition_key)

        reward = 0

        # Récompenser ou pénaliser selon le type d'attaque
        """
        type_action = transition_key.name
        if type_action.startswith("F2M"):  # passage en malware
            reward += 1
        elif type_action.startswith("F2B"):  # attaque destructive
            reward += 2
        elif type_action.startswith("F2N"):  # deni de service
            reward += 1
        elif type_action.startswith("Fall"):  # attaque en cascade
            reward += 1"""

        # Récompense si un secret est volé
        if transition_key.update.secretChange:
            reward += 2

        # Récompense si objectif atteint
        for target in self.target_index:
            if self.automata.currentLoc[target] != Location.FUNC:  # mettre == self.target_state si on veut spécifier un état précis de la cible
                print(f"--------------------attaque sur le module N°{target} réussie--------------------------")
                self.searching = False
                reward += 100
                break

        # Favoriser les couts réduits
        # reward -= int(transition_key.cost/10)
        # print("reward", reward)

        return reward

    # Renvoie True si le prochain pas est possible, False Sinon
    def more(self):

        if not self.automata.next(self.max_cost):  # aucune transitions n'est possible au prochain pas
            return False

        elif self.current_step == self.max_steps:  # nb de pas max atteint
            return False

        else:
            return self.searching  # cible atteinte dans la fonction execute

    def is_dynamic(self):
        return True
