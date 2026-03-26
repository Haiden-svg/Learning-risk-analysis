import torch
from torch.optim.lr_scheduler import ReduceLROnPlateau
from collections import deque
import random
from typing import List,Optional
from model import Model
from automata import Automata
from traces import Traces,Trace
import json
from automaton import ActiveTransition,Location, Actions, Trans, SetSecr
import sys
from datetime import datetime
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from batchInit import InitBatch
from interActiveInit import InteractiveInit
from abc import ABC
import os


if torch.cuda.is_available():
    torch.set_default_device('cuda')
else:
    torch.set_default_device('cpu')
#torch.set_default_device('cpu')


torch.set_default_dtype(torch.double)



class Empty:
    pass

# Environnement Uppaal
class UpppaalEnv:
    def __init__(self,system: Model,initialLoc:List[Location],initialtSecr: List[bool],finalState:Actions, maxTraceLen:int) -> None:

        self.automata: Automata = Automata(system,initialLoc,initialtSecr)
        self.maxTraceLen=maxTraceLen
        self.state_size: int = system.nbNodes+system.nbSecrets + 2
        self.action_size: int = sum([len(self.automata.nodes[i].automaton[loc]) for i in range(system.nbNodes) for loc in self.automata.nodes[i].automaton]) 
        self.finalState:Actions = finalState
        self.resetTraces()

    def resetState(self,initialLoc,initialtSecr):
        self.automata.reset(initialLoc,initialtSecr)
        return

    def resetTraces(self):
        self.traces:Traces=Traces(self.automata,self.maxTraceLen)
        self.savedAchievedTraces=deque(maxlen=int(self.maxTraceLen/2))
        return

    def saveTrace(self, action:ActiveTransition,stepN:int) ->None:
        self.traces.saveTransition(action,stepN)

    def step(self, action:ActiveTransition) -> None: 
        self.automata.do(action)
        return

    def done(self) -> bool:
        alreadyOK:List[bool] =[False for i in range(self.automata.nbNodes) ] 
        for trans in self.finalState.transitions:
            if self.automata.currentLoc[trans.softComp] == trans.location or alreadyOK[trans.softComp] :
                alreadyOK[trans.softComp]=True
                continue
            return False
        for secret in self.finalState.secretChange:
            if secret.val == self.automata.currentSecr[secret.secr] :
                continue
        return True

    def updateDeadloc(self) -> None:
        if (length:=len(self.traces.traces)) > 0:
            self.traces.traces[length-1].deadlock=True
        return

    def updateDone (self) -> None:
        if (length:=len(self.traces.traces)) > 0:
            self.traces.traces[length-1].done=True
        return


 # Modèle DQN (réseau de neurones)
class DQNModelSimple(nn.Module):
    def __init__(self, state_size: int, action_size: int):
        super(DQNModelSimple, self).__init__()
        self.fc1 = nn.Linear(state_size, 64)
        self.fc2 = nn.Linear(64, 64)
        self.fc3 = nn.Linear(64, action_size, bias=False)

    def forward(self, state):
        x = torch.tanh(self.fc1(state))
        x = torch.sigmoid (self.fc2(x))
        return self.fc3(x)




class MultiInputModel(nn.Module): 
    def __init__(self, env:UpppaalEnv,maxCost:int):
        self.maxCost=maxCost
        self.system:Model=env.automata.model
        super(MultiInputModel, self).__init__()
        self.secrIndex:List[List[int]]=[ [] for _ in range(self.system.nbNodes)]
        self.nodeEntries:List[int]=[ 3 + self.system.nodes[i].nbInputs for i in range(self.system.nbNodes)]
        for i in range(self.system.nbNodes):
            secrDep=[False for _ in range(self.system.nbSecrets)]
            for r in range( self.system.nodes[i].nbRoles):
                for j in range(self.system.nbSecrets):
                    kernInd=self.system.nodes[i].kernelIndex
                    if kernInd is None : kernelPart=False # for bar metal component
                    else :  kernelPart=self.system.nodes[kernInd].secrStore[j]
                    if not (
                        self.system.nodes[i].secrStore[j] or kernelPart
                        ) and self.system.nodes[i].roles[r].sessionProtectSecretIndex[j]:
                       secrDep[j]=True
            for j in range(self.system.nbSecrets):  
                if secrDep[j]:
                    self.secrIndex[i].append(j)
                    self.nodeEntries[i]+=1
        self.layers = nn.ModuleList([nn.Linear(self.nodeEntries[i], 1) for i in range(self.system.nbNodes)])
        self.final = nn.Linear(self.system.nbNodes, env.action_size, bias=False)

    def split(self,state:torch.tensor) -> list[torch.tensor]:
        tensList:List[torch.tensor]=[]
        for i in range(self.system.nbNodes):
            nx=state[:,i:i+1]  # the state of the node
            ni=state[ # current cost and current step
                :,self.system.nbNodes+self.system.nbSecrets:self.system.nbNodes+self.system.nbSecrets+2
                ] 
            nx=torch.cat((nx,ni),1)
            for j in range( self.system.nodes[i].nbInputs ): # states of the inputs nodes
                y=self.system.nodes[i].inputs[j].sourceNodeIndex
                ni=state[:,y:y+1]
                nx=torch.cat((nx,ni),1)
            for l in self.secrIndex[i]: # states of secrets, no stored on the node or ist kernel and protectings the node roles
                y=l+self.system.nbNodes
                ni=state[:,y:y+1]
                nx=torch.cat((nx,ni),1)
            tensList.append(nx)
        return tensList

    def forward(self, state):
        # Concaténation des deux entrées
        x=self.split(state) # splt of entry tensor to dependent nodes
        processed = [torch.tanh(layer(inp)) for layer, inp in zip(self.layers, x)]  
        y = torch.cat(processed, dim=-1)  # Concatène sur la dernière dimension
        return 500 * torch.sigmoid(self.final(y))



class DQNModelWK(nn.Module):  
    def __init__(self, state_size: int, action_size: int, nb_automata: int, maxCost: int):
        super(DQNModelWK, self).__init__()
        self.network = nn.Sequential(
           nn.Linear(state_size, nb_automata),
           nn.Tanh(),
           nn.Linear(nb_automata, 64),
           nn.Tanh(),
           nn.Linear(64, action_size),
           nn.Sigmoid()
        )
        self.maxCostD = maxCost*2

    def forward(self, state):
        return self.maxCostD * self.network(state)


class DQNModel(nn.Module):
    def __init__(self, state_size: int, action_size: int):
        super(DQNModel, self).__init__()
        self.fc1 = nn.Linear(state_size, 64)
        self.fc2 = nn.Linear(64, 64)
        self.raw_weight = nn.Parameter(torch.randn(action_size, 64))  # Poids sans contrainte
        self.raw_bias = nn.Parameter(torch.randn(action_size))       # Biais sans contrainte

        # Initialisation des poids
        nn.init.xavier_uniform_(self.raw_weight)
        nn.init.zeros_(self.raw_bias)

    def forward(self, state):
        # Étapes de transformation
        x = torch.tanh(self.fc1(state))         # Activation Tanh
        x = torch.sigmoid(self.fc2(x))         # Activation Sigmoid
        weight = F.softplus(self.raw_weight)   # Contrainte de non-négativité
        bias = F.softplus(self.raw_bias)       # Contrainte de non-négativité
        return F.linear(x, weight, bias)       # Calcul linéaire avec contrainte

# Agent DQN
class DQNAgent:
    def __init__(self, env:UpppaalEnv, maxCost:int) -> None:
        self.state_size: int = env.state_size
        self.action_size: int = env.action_size
        self.env:UpppaalEnv = env
        self.epsilon: float = 1 # Taux d'exploration
        self.epsilon_min: float = 0.005
        self.epsilon_decay: float = 0.9998
        self.learning_rate: float = 0.001
        #self.model: DQNModel =  DQNModelSimple(self.state_size, self.action_size)
        self.model=MultiInputModel(env,maxCost)
        #self.model: DQNModel =  DQNModelWK(self.state_size, self.action_size,env.automata.nbNodes,maxCost)
        self.criterion = nn.MSELoss()  # Erreur quadratique moyenne
        self.optimizer = optim.SGD(self.model.parameters(), lr=0.001)  # Descente de gradient stochastique
        self.scheduler = ReduceLROnPlateau(self.optimizer, mode='min', factor=0.1, patience=10)
        self.loss = None



    def selectAction(self, maxCost:int,step:int, stat:bool) -> Optional[ActiveTransition]  :  # None == deadlock 
        lnext: List[ActiveTransition] = self.env.automata.next(maxCost)
        if (length:=len(lnext))>0:
            if random.random() < self.epsilon and stat:
                # statistical choice of the transition
                return lnext[random.randint(0, length-1)]
            self.model.eval()
            with torch.no_grad():
                stateNewTarget = torch.tensor( [
                   [float(self.env.automata.currentLoc[i].value) for i in range(self.env.automata.nbNodes)] + 
                   [float(self.env.automata.currentSecr[i]) for i in range(self.env.automata.nbSecrets)] + 
                   [float(self.env.automata.currentCost)]+ [float(step)] 
                   ] )
                qValNewPred = self.model(stateNewTarget)
                #qvMin,_= torch.min(qValNewPred[0],0)
                # filtering of non active transitions  
                ind:int=-1
                valMin=0
                for k in range(length):
                    val=qValNewPred[0][lnext[k].transIndex]
                    if ind<0 or val<valMin:
                        ind=k
                        valMin=val
                return lnext[ind]     
        return None  # dead lock 

    def replay(self, batch_size: int, maxCost:int) -> None:  
        for k in range(batch_size):
            lng=len(self.env.traces.traces)
            tr=self.env.traces.traces[lng-1-k] 
            if tr.done or tr.deadlock:
                #assert not (tr.done and tr.costs>maxCost)
                self.env.savedAchievedTraces.append(tr) 
        if (nbOk:=len(self.env.savedAchievedTraces))>int(batch_size):
            nbOk=int(batch_size)
        nbSuppl=batch_size-nbOk

        traceSample:List[Trace] = (
            random.sample(self.env.traces.traces, batch_size)  + random.sample(self.env.savedAchievedTraces, nbOk) + 
            random.sample(self.env.traces.traces, nbSuppl) )
        #traceSample = self.env.traces.traces
        assert len(traceSample) == 2*batch_size

        # Tensor of states for prediction
        statesTR = torch.tensor( [ 
            [float(trace.locations[i].value) for i in range(self.env.automata.nbNodes)] + 
            [float(trace.secrets[i]) for i in range(self.env.automata.nbSecrets)] + 
            [float(trace.costs)]+ [float(trace.step)]  for trace in traceSample ] )
        # q-values predictions
        self.model.eval()
        qValpred = self.model(statesTR)   
        with torch.no_grad():
            # creation of new targets for predictions
            # 1.list of traces, states  for Bellman equation  
            StatesForNewPred = []
            for i in range(len(traceSample)):
                trace=traceSample[i]
                if trace.deadlock or trace.done:
                    continue
                locations:List[Location] = trace.locations.copy()
                secrets:List[bool]=trace.secrets.copy()
                # next state calculus
                for tr in trace.transition.update.transitions:
                    locations[tr.softComp]=tr.location
                for secr in trace.transition.update.secretChange:
                    secrets[secr.secr]=secr.val           
                traceN=Empty()
                traceN.locations=locations
                traceN.secrets=secrets
                traceN.costs=trace.costs+trace.transition.cost
                traceN.step=trace.step+1
                StatesForNewPred.append(traceN)

            stateNewTarget = torch.tensor( [ 
                [float(tr.locations[i].value) for i in range(self.env.automata.nbNodes)] +
                [float(tr.secrets[i]) for i in range(self.env.automata.nbSecrets)] + [float(tr.costs)]+ [float(tr.step)] 
                for tr in StatesForNewPred] )

            qValNewPred = self.model(stateNewTarget)
            self.model.train()
            j=0
            qValTarget=qValpred.clone()
            for i in range(len(traceSample)):
                sample=traceSample[i]
                if sample.deadlock:
                    val=500
                elif sample.done:
                    val=float(trace.transition.cost)
                else:
                    qvMin,_= torch.min(qValNewPred[j],0)
                    val=float(sample.transition.cost)+float(qvMin)
                    j+=1
                qValTarget[i][sample.transition.transIndex]=val
             
        # Entraînement sur tout le batch en une seule fois
        #self.model.train()
        loss=self.criterion(qValpred, qValTarget)
        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()
        self.loss=loss
        
        # Décroissance du taux d'exploration (epsilon)
        if self.epsilon > self.epsilon_min:
            self.epsilon *= self.epsilon_decay






class KeyboardBase(ABC):
    def __init__(self,agent:DQNAgent):
        self.debugOn = False
        self.__stop__ = False
        self.debugType = '*'  # Achieved
        self.agent=agent
    def debug(self,mode:str) -> bool:
        sTyped=False
        kTyped=False
        if self.testKey():
            kTyped=True
            if self.getChar() == b'S':
                sTyped=True
                self.debugType = '*'
        if not self.debugOn and not kTyped:
            return False

        if ( (self.debugType != "*") and (mode != self.debugType) and self.debugOn ) and not sTyped:
            return False
        if self.debugType != '*':
            self.debugType = mode
        self.flush_input()
        s=input(f" Debug mode:{self.debugType}, 'E' epsilon,'S' to stop, 'N' no debug, 'A': achieved, 'D': deadlocks, 'R': replays, 'F'  non achieved , '*' all ? ").lstrip().capitalize()
        if s.startswith('S'):
            s=input(" Stop ?, 'Y' to confirm ?  ").lstrip().capitalize()
            if s.startswith('Y'):
                self.__stop__=True
                return False
        elif s.startswith('N'):
                self.debugOn = False
                return(False)
        elif s.startswith('E'):
            s=input(f" Current epsilon: {self.agent.epsilon}, new value or 'return' ").lstrip().capitalize()
            s1=input(f" Current epsilon_decay: {self.agent.epsilon_decay}, new value or 'return' ").lstrip().capitalize()
            try:
                if s=='': r=self.agent.epsilon
                else: r=float(s)
                if s1=='': r1=self.agent.epsilon_decay
                else: r1=float(s1)
                if r>=0 and r<=1 and r1>0 and r1<=1:
                    self.agent.epsilon=r
                    self.agent.epsilon_decay=r1
                else: print("bad value")
            except ValueError:
                print("bad value")
            return False
        if s.startswith('A'):
            self.debugType = 'A'
        elif s.startswith('D'):
            self.debugType = 'D'
        elif s.startswith('R'):
            self.debugType = 'R'
        elif s.startswith('F'):
            self.debugType = 'F'
        elif s.startswith('*'):
            self.debugType = '*'
        self.debugOn = True
        return (self.debugType == mode) or (self.debugType=='*')
    def stop(self):
        return self.__stop__

if os.name == 'nt':
    import msvcrt
    class Keyboard(KeyboardBase):
        def testKey(self) -> bool:
            return (msvcrt.kbhit())
        def flush_input(self):
            while msvcrt.kbhit():
                msvcrt.getch()
        def getChar(self):
            return msvcrt.getch()
else:
    import select
    import termios
    import getch
    class Keyboard(KeyboardBase):
        def testKey(self) -> bool:
            return(select.select([sys.stdin], [], [], 0) == ([sys.stdin], [], []))
        def flush_input(self):
            termios.tcflush(sys.stdin, termios.TCIOFLUSH)
        def getChar(self):
            return getch.getch()


class DQNtask :

    def __init__(self, systemPath: str, maxCost:int, batch_size:int,episodes:int,maxEpisodeLength:int,maxTraceLen:int):

        # system Init

        #json file parsing 
        with open(systemPath, "r") as JsonFile:
            data = json.load(JsonFile)
        system: Model = Model(**data)

        if system.nbNodes is None:
            print ("no nodes in the architecture")
            return None
        elif system.nbNodes <=0:
            print ("no nodes in the architecture")
            return None

        if system.nbSecrets is None:
            system.nbSecrets=0
        if system.nbSecrets <0 :
            system.nbSecrets=0

        self.system=system

        batchFilePath = systemPath.replace(".json",".start")

        if batchFilePath is None:
            batchInter=True
        else:
            initBatch=InitBatch(batchFilePath,system)
            batchInter = initBatch.cr != 0 

        if batchInter:
   
            print ("No batch initialization")

            interInit:InteractiveInit=InteractiveInit(system)

            self.initialLoc:List[Location]= interInit.initLocality()

            self.initialtSecr:List[bool]=interInit.initSecrets()

            #  état final souhaité 
            # 
            self.finalState:Actions=interInit.initTarget()
        else:
            self.initialLoc=initBatch.initialLoc
            self.initialtSecr=initBatch.initialtSecr
            self.finalState=initBatch.finalState
            print("Initialized by batch")
            print(initBatch)

        self.maxCost=maxCost

        self.batch_size = batch_size
        self.maxTraceLen = maxTraceLen

        self.env = UpppaalEnv(self.system,self.initialLoc,self.initialtSecr,self.finalState,self.maxTraceLen)

        self.agent = DQNAgent(self.env,maxCost)

        self.episodes = episodes
        self.maxEpisodeLength = maxEpisodeLength
        self.tKeyMon = Keyboard(self.agent) # monitoring keboard start

    
    def learning(self): #learning phase

        strTime=datetime.now()
        print("Start Time =", strTime.strftime("%H:%M:%S"))
        if self.episodes==0 or self.env.done() or self.agent.selectAction(self.maxCost,0,True) is None  or self.batch_size<1 or self.maxEpisodeLength <= 0:
            print("poorly defined problem")
            return(2) # poorly defined problem
      
        nbNewTraces=0   
        nbachieved=0
        nbDeadLock=0
        nbNonAchieved=0
        nbReplay=0


        for e in range(self.episodes):
            deadLock=False
            achieved=False
            self.env.resetState(self.initialLoc,self.initialtSecr)
            for step in range(self.maxEpisodeLength):
                assert nbNewTraces <= self.batch_size
                action = self.agent.selectAction(self.maxCost,step,True)
                if action is None :
                    assert step > 0
                    nbDeadLock+=1
                    if self.tKeyMon.debug("D") :
                        print(f"Deadlock at step: {step}  Episode: {e}/{self.episodes}, epsilon: {self.agent.epsilon:.2f}, Loss: {self.agent.loss.item():.6f}, nb non achieved={nbNonAchieved}, nb achieved={nbachieved} nb deadLock={nbDeadLock} , nb replay={nbReplay}, cost={self.env.automata.currentCost}, maxCost={self.maxCost}")
                        l=len(self.env.traces.traces)
                        for i in range(step+1):
                            print (self.env.traces.traces[l-1-step+i].transition) 
                    self.env.updateDeadloc()  # previous action raised deadlock
                    deadLock=True
                    break 
                self.env.saveTrace(action,step)
                nbNewTraces+=1
                self.env.step(action)
                if self.env.done() :
                    nbachieved+=1
                    self.env.updateDone()
                    if self.tKeyMon.debug("A") :
                        print(f"Target achieved at step {step}  Episode: {e}/{self.episodes}, epsilon: {self.agent.epsilon:.2f}, Loss: {self.agent.loss.item():.6f}, nb non achieved={nbNonAchieved}, nb achieved={nbachieved} nb deadLock={nbDeadLock} , nb replay={nbReplay}, cost={self.env.automata.currentCost}, maxCost={self.maxCost}")
                        l=len(self.env.traces.traces)
                        for i in range(step+1):
                            print (self.env.traces.traces[l-1-step+i].transition) 
                    self.maxCost = self.env.automata.currentCost   #  may be ?
                    achieved=True         
                if nbNewTraces == self.batch_size :
                    nbReplay+=1
                    if self.tKeyMon.debug("R") :
                        print(f"Replay, Episode:  {e}/{self.episodes}")
                    self.agent.replay(self.batch_size,self.maxCost)
                    nbNewTraces=0
                if achieved:
                    break
                if self.tKeyMon.stop():
                    break
            if not deadLock and not achieved:
                nbNonAchieved+=1
                if self.tKeyMon.debug("F") :
                    print(f"Target non achieved at step : {step}  Episode: {e}/{self.episodes}, epsilon: {self.agent.epsilon:.2f}, Loss: {self.agent.loss.item():.6f}, nb non achieved={nbNonAchieved}, nb achieved={nbachieved} nb deadLock={nbDeadLock} , nb replay={nbReplay}, cost={self.env.automata.currentCost}, maxCost={self.maxCost}")
                    l=len(self.env.traces.traces)
                    for i in range(step+1):
                        print (self.env.traces.traces[l-1-step+i].transition)
                self.env.updateDeadloc()
            if e%200==0 :
                if self.agent.loss is None:
                    print(f" Episode: {e}/{self.episodes}, epsilon: {self.agent.epsilon:.2f}, nb non achieved={nbNonAchieved}, nb achieved={nbachieved} nb deadLock={nbDeadLock} , nb replay={nbReplay}, maxCost={self.maxCost}")
                else:
                    print(f" Episode: {e}/{self.episodes}, epsilon: {self.agent.epsilon:.2f}, Loss: {self.agent.loss.item():.6f}, nb non achieved={nbNonAchieved}, nb achieved={nbachieved} nb deadLock={nbDeadLock} , nb replay={nbReplay}, cost={self.env.automata.currentCost}, maxCost={self.maxCost}")
            if self.tKeyMon.stop():
                break
        if self.tKeyMon.stop():
            print ("Learning stopped")
        endLearnTime=datetime.now()
        print("lengt of learning =", endLearnTime.strftime("%H:%M:%S"))
        print(f"after{endLearnTime-strTime}")  

    def application(self) ->int:      # Exploitation de l'agent DQN
        print("Exploitation")
        self.env.resetState(self.initialLoc,self.initialtSecr)
        self.env.resetTraces()

        for step in range(self.maxEpisodeLength):
            if self.env.done() :
                print(f"Target achieved, step: {step}, cost={self.env.automata.currentCost}")
                break 
            action = self.agent.selectAction(self.maxCost,step,False)
            if action==None :
                print(f"Deadlock, step: {step}, cost={self.env.automata.currentCost}")
                break         
            done = False
            self.env.saveTrace(action,step)
            self.env.step(action)   
        inp=input("Simulation completed, press enter to get traces")
        for step in self.env.traces.traces:
            print(step.transition)
        return 0


def main() -> int:
    # Entraînement de l'agent DQN
    batch_size: int = 64
    episodes: int = 1000000
    maxEpisodeLength:int  = 8
    maxCost:int=300
    maxTraceLen = batch_size*3
    task=DQNtask("./jsons/ResilientCarMonV5.json",maxCost,batch_size,episodes,maxEpisodeLength,maxTraceLen)
    if task==None:
        return (1)
    task.learning()
    task.application()
    return(0)


if __name__ == "__main__":
    sys.exit(main())
