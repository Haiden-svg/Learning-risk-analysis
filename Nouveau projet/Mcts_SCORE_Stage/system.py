from model import Model
from typing import List
from automaton import ActiveTransition, Location
from automata import Automata, Actions
from traces import Traces
import json
import sys
from batchInit import InitBatch
from interActiveInit import InteractiveInit
import os
import random

if os.name == 'nt':
    import msvcrt


    class Keyboard():
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


    class Keyboard():
        def testKey(self) -> bool:
            return (select.select([sys.stdin], [], [], 0) == ([sys.stdin], [], []))

        def flush_input(self):
            termios.tcflush(sys.stdin, termios.TCIOFLUSH)

        def getChar(self):
            return getch.getch()


def done(automata, finalState) -> bool:
    alreadyOK: List[bool] = [False for i in range(automata.nbNodes)]
    for trans in finalState.transitions:
        if automata.currentLoc[trans.softComp] == trans.location or alreadyOK[trans.softComp]:
            alreadyOK[trans.softComp] = True
            continue
        return False
    for secret in finalState.secretChange:
        if secret.val == automata.currentSecr[secret.secr]:
            continue
    return True


def main() -> int:
    global code
    systemPath = "./jsons/ResilientCarMonV5.json"  # Le model à executer

    with open(systemPath, "r") as JsonFile:
        data = json.load(JsonFile)
    system: Model = Model(**data)

    if system.nbNodes is None:
        print("no nodes in the architecture")
        exit(1)
    elif system.nbNodes <= 0:
        print("no nodes in the architecture")
        exit(1)

    if system.nbSecrets is None:
        system.nbSecrets = 0

    batchFilePath = systemPath.replace(".json", ".start")

    if batchFilePath is None:
        batchInter = True
    else:
        initBatch = InitBatch(batchFilePath, system)
        batchInter = initBatch.cr != 0

    if batchInter:

        print("No batch initialization")

        interInit: InteractiveInit = InteractiveInit(system)

        initialLoc: List[Location] = interInit.initLocality()

        initialtSecr: List[bool] = interInit.initSecrets()

        #  état final souhaité 
        # 
        finalState: Actions = interInit.initTarget()
    else:
        initialLoc = initBatch.initialLoc
        initialtSecr = initBatch.initialtSecr
        finalState = initBatch.finalState
        print("Initialized by batch")
        print(initBatch)

    netAutomata: Automata = Automata(system, initialLoc, initialtSecr)

    if done(netAutomata, finalState):
        print("Initial state == Final State")
        exit(1)

    for i in range(netAutomata.nbNodes): print(f"{netAutomata.nodes[i].node.name, netAutomata.currentLoc[i].name}")

    maxCost: int = 95
    maxTraceLen: int = 2000
    inp: str = ""
    step: int = 0
    stop: bool = False
    achieved: bool = False
    deadlock: bool = False
    automChoice = False
    maxEpisodeLength: int = 6
    tKeyMon = Keyboard()
    nbEpisode: int = 0
    optTraces: Traces = None

    while not stop:
        netAutomata.reset(initialLoc, initialtSecr)
        traces: Traces = Traces(netAutomata, maxTraceLen)
        step = 0
        achieved = False
        deadlock = False
        nbStep = 0
        nbNext = 0
        while step < maxEpisodeLength:
            lnext: List[ActiveTransition] = netAutomata.next(maxCost)
            import os

            def clear_console():
                os.system('cls' if os.name == 'nt' else 'clear')

            """
            print("Mini shell Python — tape 'exit' pour quitter, 'clear' pour nettoyer l'écran")
            while True
                try:
                    code = input(">>> ")
                    if code.strip() in ("exit", "quit"):
                        break
                    if code.strip() == "clear":
                        clear_console()
                        continue
                    result = eval(code)
                    if result is not None:
                        print(result)
                except SyntaxError:
                    try:
                        exec(code)
                    except Exception as e:
                        print("Erreur :", e)
                except Exception as e:
                    print("Erreur :", e)"""

            if len(lnext) > 0:
                nbNext += len(lnext)
                if automChoice:
                    if tKeyMon.testKey():
                        if tKeyMon.getChar() == b'S':
                            automChoice = False
                    tKeyMon.flush_input()
                    if automChoice:
                        k = random.randint(0, len(lnext) - 1)
                if not automChoice:
                    os.system('cls')
                    print(f"Total cost : {netAutomata.currentCost} for max:{maxCost},  Available transitions:")
                    for i in range(len(lnext)):
                        print(f"Transition {i}:  {lnext[i]}")
                    inp = input(
                        "Transition number to fire or 'End' to stop, 'Trace' to get trace of achieved episode, "
                        "'Restart' to restart episode, 'Auto' for automatic transition choice ")
                    inp = inp.upper()
                    if inp.startswith("A"):
                        automChoice = True
                        continue
                    elif inp.startswith("E"):
                        stop = True
                        break
                    elif inp.startswith("R"):
                        break
                    elif inp.startswith("T"):
                        if optTraces is None:
                            print("No solution found")
                        else:
                            print(f"Best solution, Number of steps {len(optTraces.traces)}, Total cost:{maxCost}")
                            for tr in optTraces.traces:
                                print(tr.transition)
                        input("return to continue")
                        continue
                    k = -1
                    if inp.isnumeric():
                        k = int(inp)
                    if k < 0 or k >= len(lnext):
                        input("Bad transition number, press enter to continue")
                        continue
                traces.saveTransition(lnext[k], step)
                netAutomata.do(lnext[k])
                step += 1
                if done(netAutomata, finalState):
                    achieved = True
                    if optTraces is None or netAutomata.currentCost < maxCost or len(traces.traces) < len(
                            optTraces.traces):
                        optTraces = traces
                    maxCost = netAutomata.currentCost
                    break
                if step == maxEpisodeLength:
                    break
            else:
                print(
                    f"Episode:{nbEpisode} Deadlock, Number of steps {len(traces.traces)}, Total cost:{netAutomata.currentCost}")
                deadlock = True
                break
        nbStep += len(traces.traces)
        if (not stop and achieved) or nbEpisode % 200 == 0:
            meanNBaction = nbNext / nbStep
            if achieved:
                txt = "\aTarget achieved"
            elif deadlock:
                txt = "Deadlock"
            elif step == maxEpisodeLength:
                txt = "Episode too long"
            print(
                f"\nEpisode:{nbEpisode} {txt}, Number of steps {len(traces.traces)}, Costs / maxCost: {netAutomata.currentCost} / {maxCost}, min nb actions:{meanNBaction:.0f}")
            for tr in traces.traces:
                print(tr.transition)
            if achieved:
                input("\areturn to continue")
        nbEpisode += 1
    inp = input("Simulation completed, press enter to get trace")
    if optTraces is None:
        print("No solution found")
        return 0
    print(f"Number of steps {len(optTraces.traces)}, Total cost:{maxCost}")
    for tr in optTraces.traces:
        print(tr.transition)
    return 0


if __name__ == "__main__":
    sys.exit(main())
