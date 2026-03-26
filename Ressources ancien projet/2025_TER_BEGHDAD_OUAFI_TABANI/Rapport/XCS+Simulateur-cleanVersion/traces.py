from automaton import Location, ActiveTransition, Actions, Trans,SetSecr
from automata import Automata
from typing import List
from collections import deque


class Trace:
    cost: int
    locations: List[Location]
    secrets: List[bool]
    transition:ActiveTransition

    def __init__(self,transition:ActiveTransition):
        self.locations:List[Location] = []
        self.secrets:List[bool] = []
        self.transition:ActiveTransition=transition
        self.deadlock:bool=False
        self.done:bool=False
        self.costs:int=0 # cumulated costs 
        self.step:int=0


class Traces:
    netAutomata: Automata
    traces: deque[Trace]
    
    def __init__(self, netAutomata: Automata,maxLen:int):

        self.netAutomata=netAutomata
        self.traces=deque(maxlen=maxLen)

    def saveTransition(self,transition:ActiveTransition,step:int):
        # save current state to traces
        currentTr: Trace = Trace(transition)
        currentTr.costs=self.netAutomata.currentCost
        currentTr.step=step
        for i in range(self.netAutomata.nbNodes):
            currentTr.locations.append(self.netAutomata.currentLoc[i])
        for i in range(self.netAutomata.nbSecrets):
            currentTr.secrets.append(self.netAutomata.currentSecr[i])
        self.traces.append(currentTr)

