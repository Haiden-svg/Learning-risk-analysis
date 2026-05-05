import json
import sys
from model import Model
from batchInit import InitBatch
from interActiveInit import InteractiveInit
from mcts_agent import MCTSAgent
from uppaal_env import UpppaalEnv # On garde ton environnement Uppaal qui gère l'automate

class MCTSTask:
    def __init__(self, systemPath: str, maxCost: int, num_iterations: int, maxEpisodeLength: int, maxTraceLen: int):
        # 1. Chargement du JSON
        with open(systemPath, "r") as JsonFile:
            data = json.load(JsonFile)
        self.system = Model(**data)

        if self.system.nbNodes is None or self.system.nbNodes <= 0:
            print("Erreur : Aucun noeud dans l'architecture.")
            sys.exit(1)

        if self.system.nbSecrets is None or self.system.nbSecrets < 0:
            self.system.nbSecrets = 0

        # 2. Initialisation (Batch ou Interactive)
        batchFilePath = systemPath.replace(".json", ".start")
        initBatch = InitBatch(batchFilePath, self.system) if batchFilePath else None
        
        if initBatch is None or initBatch.cr != 0:
            print("Pas d'initialisation Batch, passage en mode interactif.")
            interInit = InteractiveInit(self.system)
            self.initialLoc = interInit.initLocality()
            self.initialtSecr = interInit.initSecrets()
            self.finalState = interInit.initTarget()
        else:
            self.initialLoc = initBatch.initialLoc
            self.initialtSecr = initBatch.initialtSecr
            self.finalState = initBatch.finalState
            print("Initialisé par le fichier Batch.")

        # 3. Paramètres
        self.maxCost = maxCost
        self.maxEpisodeLength = maxEpisodeLength
        self.maxTraceLen = maxTraceLen

        # 4. Création de l'Environnement et de l'Agent MCTS
        self.env = UpppaalEnv(self.system, self.initialLoc, self.initialtSecr, self.finalState, self.maxTraceLen)
        self.agent = MCTSAgent(self.env, maxCost, num_iterations=num_iterations)

    def run_simulation(self) -> int:
        print("\n--- Démarrage de l'exploitation MCTS ---")
        self.env.resetState(self.initialLoc, self.initialtSecr)
        self.env.resetTraces()

        for step in range(self.maxEpisodeLength):
            if self.env.done():
                print(f"\n[SUCCÈS] Cible atteinte à l'étape {step} ! Coût total : {self.env.automata.currentCost}")
                break 
                
            # C'est ici qu'on appelle notre MCTS !
            action = self.agent.selectAction(self.maxCost, step, False)
            
            if action is None:
                print(f"\n[ÉCHEC] Deadlock à l'étape {step}. Coût total : {self.env.automata.currentCost}")
                break         
                
            self.env.saveTrace(action, step)
            self.env.step(action)   
            
        print("\n--- Simulation terminée. Traces du chemin d'attaque : ---")
        for trace in self.env.traces.traces:
            print(trace.transition)
        return 0

def main() -> int:
    # Paramètres
    maxCost = 300
    maxEpisodeLength = 8
    num_mcts_iterations = 1000 # Nombre de simulations par décision
    
    # Remplacer par le bon chemin vers ton JSON
    json_path = "/jsons/ResilientCarMonV5.json" 
    
    task = MCTSTask(json_path, maxCost, num_iterations=num_mcts_iterations, maxEpisodeLength=maxEpisodeLength, maxTraceLen=100)
    task.run_simulation()
    
    return 0

if __name__ == "__main__":
    sys.exit(main())