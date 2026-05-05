from typing import List
from collections import deque
from model import Model
from automata import Automata
from traces import Traces
from automaton import ActiveTransition, Location, Actions

class UpppaalEnv:
    def __init__(self, system: Model, initialLoc: List[Location], initialtSecr: List[bool], finalState: Actions, maxTraceLen: int) -> None:
        self.automata: Automata = Automata(system, initialLoc, initialtSecr)
        self.maxTraceLen = maxTraceLen
        self.state_size: int = system.nbNodes + system.nbSecrets + 2
        
        # Calcul du nombre d'actions
        self.action_size: int = sum([len(self.automata.nodes[i].automaton[loc]) for i in range(system.nbNodes) for loc in self.automata.nodes[i].automaton]) 
        
        self.finalState: Actions = finalState
        self.resetTraces()

    def resetState(self, initialLoc, initialtSecr):
        self.automata.reset(initialLoc, initialtSecr)
        return

    def resetTraces(self):
        self.traces: Traces = Traces(self.automata, self.maxTraceLen)
        self.savedAchievedTraces = deque(maxlen=int(self.maxTraceLen/2))
        return

    def saveTrace(self, action: ActiveTransition, stepN: int) -> None:
        self.traces.saveTransition(action, stepN)

    def step(self, action: ActiveTransition) -> None: 
        self.automata.do(action)
        return

    def done(self) -> bool:
        alreadyOK: List[bool] = [False for i in range(self.automata.nbNodes)] 
        for trans in self.finalState.transitions:
            if self.automata.currentLoc[trans.softComp] == trans.location or alreadyOK[trans.softComp]:
                alreadyOK[trans.softComp] = True
                continue
            return False
        for secret in self.finalState.secretChange:
            if secret.val == self.automata.currentSecr[secret.secr]:
                continue
        return True

    def updateDeadloc(self) -> None:
        if (length := len(self.traces.traces)) > 0:
            self.traces.traces[length-1].deadlock = True
        return

    def updateDone (self) -> None:
        if (length := len(self.traces.traces)) > 0:
            self.traces.traces[length-1].done = True
        return