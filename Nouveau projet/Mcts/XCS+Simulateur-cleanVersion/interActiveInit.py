import os
from typing import Tuple, List,Optional
from model import Model
from automaton import Location, Actions, Trans, SetSecr



class InteractiveInit():
    def __init__(self,system:Model):
        self.system=system

    def initLocality(self) -> List[Location]:
        initialLoc: List[Location]=[Location.FUNC for i in range(self.system.nbNodes)]
        os.system('cls')
        while True: # for nodes 
            k:int=0
            print ("Initial node states", end =" : ")
            for i in range (self.system.nbNodes):
                print(f"{i}={self.system.nodes[i].name}:{initialLoc[i]}",end=':')
            print()
            inp=input("which node number to change:")
            if not inp.isnumeric():
                break
            if int(inp) <0 or int(inp)>=self.system.nbNodes:
                continue
            print("what location ?   ",end="")
            for loc in Location:
                print (f"{loc.value}:{loc.name}", end="?  ")
            inp1=input()
            if not inp1.isnumeric():
                continue
            if int(inp1) >0 and int(inp1) <4:
                initialLoc[int(inp)]=Location(int(inp1)) 
        return initialLoc

    def initSecrets(self) -> List[bool]:
        initialtSecr: List[bool]=[False for i in range(self.system.nbSecrets)]
        while True: # for secrets 
            k:int=0
            print ("Initial secrets states", end =" : ")
            for i in range (self.system.nbSecrets):
                print(f"{i}={self.system.secrets[i]}:{initialtSecr[i]}",end=':')
            print()
            inp=input("which secret number to change or 'return' :")
            if not inp.isnumeric():
                break
            if int(inp) <0 or int(inp)>=self.system.nbSecrets:
                continue
            inp1=input("what value ?  F or T : ?  ").upper()
            if inp1.startswith("T") or inp1.startswith("F"):
                initialtSecr[int(inp)]=inp1.startswith("T")
        return initialtSecr

    def initTarget(self) -> Actions: 
        finalState:Actions=Actions()

        while True: # for nodes 
            k:int=0
            if len(finalState.transitions)>0:
                print ("Alreday targeted nodes' locations")
                for trans in finalState.transitions:
                    print(f"{trans.softComp}.{self.system.nodes[trans.softComp].name}:{trans.location}",end="| ")
                print()

            print ("Targeted nodes' locations", end =" : ")
            for i in range (self.system.nbNodes):
                print(f"{i}={self.system.nodes[i].name}",end=':')
            print()
            inp=input("which node number to target? ")
            if not inp.isnumeric():
                break
            if int(inp) <0 or int(inp)>=self.system.nbNodes:
                continue
            print("what location ?   ",end="")
            for loc in Location:
                print (f"{loc.value}:{loc.name}", end="?  ")
            inp1=input()
            if not inp1.isnumeric():
                continue
            if int(inp1) >0 and int(inp1) <4:
                finalState.transitions.append(Trans(int(inp),Location(int(inp1))))

        while True: # for secrets 
            k:int=0
            if len(finalState.secretChange)>0:
                print ("Alreday targeted stolen secrets")
                for secr in finalState.secretChange:
                    print(f"{secr.secr}.{self.system.secrets[secr.secr]}:{secr.val}",end="| ")
                print()

            print ("Targeted stolen secrets", end =" : ")
            for i in range (self.system.nbSecrets):
                print(f"{i}={self.system.secrets[i]}",end=':')
            print()
            inp=input("which secret number to target or 'return to end'? ")
            if not inp.isnumeric():
                break
            if int(inp) <0 or int(inp)>=self.system.nbSecrets:
                continue
            print("what value (T or F): ?   ",end="")
            inp1=input().upper()
            if inp1.startswith("T") or inp1.startswith("F") :
                # purge list if already contains the secret
                for i in range (len(finalState.secretChange)):
                    if finalState.secretChange[i].secr==int(inp):
                        del finalState.secretChange[i]
                        break
                finalState.secretChange.append(SetSecr(int(inp), inp1=="T"))

        return finalState

        