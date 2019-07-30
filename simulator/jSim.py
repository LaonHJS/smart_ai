from simulator.jSimUtil import JSimUtil
import time as time
from simulator.simRecord import *
from problemIO.problem import ProductionInfo
from problemIO.resource import *
from problemIO.lot import *
from simulator.gen_data import NormalForState
from learner.regression import *
from copy import deepcopy as cp
import sys
import random
import numpy as np
import operator


class JSim(JSimUtil):

    def __init__(self, sim_parameter, production_info: "ProductionInfo",  DA_waiting_learner=None, DA_idle_learner=None, WB_RTD_learner=None):
        JSimUtil.__init__(self, sim_parameter)
        self.DA_waiting_learner = DA_waiting_learner
        self.DA_idle_learner = DA_idle_learner
        self.WB_waiting_learner = WB_RTD_learner
        self.for_normalization = self.parameters.normFileWrite

        self.info = cp(production_info)
        self.config = self.info.config
        self.count = 0
        self.intentional_delay_level = random.uniform(0, 1)

        # Normalization 이외에는 절대 수정해서는 안 됨
        self.original_info = production_info

    def runSimul(self):
        assert isinstance(self.info, ProductionInfo)
        self.UTILCUTTIME = self.parameters.UTILCUTTIME * (self.info.simulDay * 2)
        self.setSimClock(time.time())
        self.DBTableName = self.info.DBTableName
        self.initialize()

        sim_counter = 0
        while self.toNext(sim_counter):
            sim_counter += 1
        if self.parameters.rtdTraining:
            if self.info.needDAWaitingNormalization:
                self.DA_waiting_score(self.original_info.DA_score_nor)
            if self.parameters.DARTDPolicy == 'random':
                self.rtd_score(self.original_info.score_nor)
                if self.info.needScoreNormalization is False and self.info.needStateNormalization is False:
                    self.rtd_rec.fileWrite('DA')

        totalUtilTime = 0
        avgIdle = 0
        num_of_bottleneck_res = 0
        for resourceId, utilTime in self.KPIs.Utilization.items():
            totalUtilTime += utilTime
            resUtil = utilTime / self.UTILCUTTIME
            self.sr.utilizationPerResource[resourceId] = resUtil
            currentResource = self.info.resourceMap[resourceId]
            assert isinstance(currentResource, Resource)
            self.sr.setUtilRecord(currentResource, resUtil)
            if 'WB' in resourceId:
                num_of_bottleneck_res += 1
                avgIdle += currentResource.total_idle_time
        self.sr.calUtilRecord()
        self.sr.idle_time_bottleneck = avgIdle/num_of_bottleneck_res/60
        # UTIL KPI
        self.sr.util = totalUtilTime / self.UTILCUTTIME / len(self.KPIs.Utilization)

        # Out Target KPI
        targetQuantity = 0
        productionQuantity = 0
        for productId, quantity in self.info.productionRequirement.items():
            targetQuantity += quantity
            productionQuantity += self.KPIs.completedProductQuantity[productId]
        self.sr.target_score = productionQuantity / targetQuantity

        # TAT, makespan KPI
        self.sr.makespan = self.KPIs.makespan
        self.sr.DA_makespan = self.KPIs.DA_makespan
        totalTAT = 0
        totalWaiting = 0

        for lotId, temp_lot in self.info.lotMap.items():
            if lotId in self.KPIs.TATMap:
                totalTAT += self.KPIs.TATMap[lotId]
                self.sr.setTATRecord(self.info.lotMap[lotId], self.KPIs.TATMap[lotId])
                totalWaiting += self.KPIs.waitingMap[lotId]
            else:
                assert isinstance(temp_lot, Lot)
                if temp_lot.factoryInTime > -1:
                    self.KPIs.TATMap[lotId] = self.T - temp_lot.factoryInTime
                    totalTAT += self.KPIs.TATMap[lotId]
                    if 'STOCK' in temp_lot.lotLocation or 'BUF' in temp_lot.lotLocation:
                        latestLotHistory = temp_lot.historyList[-1]
                        assert isinstance(latestLotHistory, LotHistory)
                        self.KPIs.waitingMap[lotId] += self.T - latestLotHistory.eventTime
                    totalWaiting += self.KPIs.waitingMap[lotId]

        self.sr.calTATRecord()
        self.sr.total_TAT = totalTAT / 3600
        self.sr.total_WaitingTime = totalWaiting / 3600
        self.sr.avg_WaitingTime = totalWaiting / (60 * len(self.KPIs.waitingMap))
        self.sr.avg_TAT = totalTAT / (60 * len(self.KPIs.waitingMap))
        self.sr.store_inTarget(self.info.intarget, self.counters.inTargetCompletion)
        if self.parameters.viewerFileWrite:
            self.write_lot_history()
            self.viewerWriter(self.info.config, self.sr.avg_TAT)

        return self.sr

    def toNext(self, sim_counter):
        if len(self.info.eventList) == 0:
            self.KPIs.makespan = self.T
            return False
        event = self.info.eventList[0]
        assert isinstance(event, Event)
        self.T = event.start_time + event.period_time
        if event.type == "FactoryInFinish":
            self.factoryInFinish(event)
        elif event.type == 'MoveFinish':
            self.moveFinish(event)
        elif event.type == 'TrackInFinish':
            self.KPIs.makespan = self.T
            if 'DA' in event.resourceId:
                self.counters.workingDA -= 1
                self.KPIs.DA_makespan = self.T
            if 'WB' in event.resourceId:
                self.counters.workingWB -= 1
            nowLot = self.info.lotMap[event.lotId]
            assert isinstance(nowLot, Lot)
            product_id = nowLot.productId
            if event.resourceId != "MD_RES":
                if event.start_time > self.UTILCUTTIME:
                    pass
                elif self.T > self.UTILCUTTIME:
                    temp_time = self.UTILCUTTIME - event.start_time
                    if temp_time >= 0:
                        self.KPIs.Utilization[event.resourceId] = self.KPIs.Utilization[event.resourceId] + temp_time
                else:
                    self.KPIs.Utilization[event.resourceId] = self.KPIs.Utilization[event.resourceId] + event.period_time
                self.ganttChart.scheduleForResource[event.resourceId].append(
                    Gantt(sim_counter, event.start_time, (event.start_time + event.period_time), product_id, event.lotId, nowLot.lotQuantity, nowLot.currentOperationId, nowLot.flowNumber))
                # For load analysis
                resource_type = event.resourceId[0:2]
                current_simul_day = int(self.T / self.parameters.UTILCUTTIME)
                event_start_day = int(event.start_time / self.parameters.UTILCUTTIME)
                processing_time_event = 0
                processing_time_current = 0
                if current_simul_day != event_start_day:
                    processing_time_event = current_simul_day * self.parameters.UTILCUTTIME - event.start_time
                    processing_time_current = event.period_time - processing_time_event
                else:
                    processing_time_event = event.period_time
                if len(self.production_load[product_id][resource_type]) == 0:
                    for index in range(self.info.simulDay):
                        self.production_load[product_id][resource_type].append(0)
                if event_start_day < self.info.simulDay:
                    self.production_load[product_id][resource_type][event_start_day] += processing_time_event
                if current_simul_day < self.info.simulDay:
                    self.production_load[product_id][resource_type][current_simul_day] += processing_time_current
            else:
                self.counters.ShipCount[self.T] = self.counters.shipCounter
                self.counters.shipCounter += 1
                # For state making (progress rate)
                self.counters.current_finished_lot_per_product[nowLot.productId] += nowLot.lotQuantity
            self.trackInFinish(event)
        elif event.type == 'TrackOutMoveFinish':
            self.trackOutMoveFinish(event)
        # else:
        #     return False
        waitDet = True
        while waitDet:
            waitDet = False
            for tempEvent in self.waitingEventList:
                # for event in self.info.eventList:
                #     if "Waiting" in event.type:
                if self.processWaiting(tempEvent):
                    waitDet = True
                    break
        move_waiting = True
        while move_waiting:
            move_waiting = self.processMoveWaiting()
        self.temporary_conflict_state = defaultdict(lambda: defaultdict(list))

        self.WBUtilPerTime[self.T] = self.counters.workingWB / self.num_of_resource_per_op['WB']
        self.info.eventList.sort(key=lambda x: (x.start_time + x.period_time, x.eventId))
        return True

    def factoryInFinish(self, event: "Event"):
        currentLot = self.info.lotMap[event.lotId]
        currentOperationId = currentLot.currentOperationId
        currentLot.recordHistory("FACTORY IN", self.T, "WAIT", "CST_STOCK", "", currentOperationId)
        self.appendEvent(self.give_event_number(), currentOperationId, event.lotId, "", "MoveWaiting", self.T, sys.maxsize)

    def moveFinish(self, event: "Event"):
        currentLot = self.info.lotMap[event.lotId]
        assert isinstance(currentLot, Lot)
        currentOperationId = currentLot.currentOperationId
        if currentLot.reservedSameResource:
            currentLot.reservedSameResource = False
        else:
            currentLot.recordHistory("MOVE END", self.T, "WAIT", currentLot.lotLocation, event.resourceId)
            self.update_confliting_lots(currentLot)
        if event.resourceId == 'MD_RES':
            currentLot.recordHistory("TRACK IN", self.T, "PROCESS", event.resourceId, event.resourceId)
            self.update_confliting_lots(currentLot)
            self.appendEvent(self.give_event_number(), currentOperationId, event.lotId, event.resourceId, "TrackInFinish", self.T, 300)
        else:
            currentResource = self.info.resourceMap[event.resourceId]
            assert isinstance(currentResource, Resource)
            if currentLot.flowNumber > 0:
                currentResource.reservedLotId = ''
                currentLot.reservedResourceId = ''
            if currentResource.resourceStatus == 'IDLE':  # Setup이 필요 없으면서 IDLE인 경우
                currentLot.currentOperationStartTime = self.T
                currentLot.recordHistory("TRACK IN", self.T, "PROCESS", event.resourceId, event.resourceId)
                self.update_confliting_lots(currentLot)
                currentResource.recordHistory("START PROD", self.T, "RUN", currentLot.productId, event.lotId,
                                              self.info.flowMap.get(currentLot.flowId).getNowOperation(currentLot.flowNumber),
                                              self.info.flowMap.get(currentLot.flowId).getNowOperation(currentLot.flowNumber - 1))
                # Buffer에 하나의 여유 공간이 생기므로 Feasible Resource Id Map에 없다면 추가
                self.updateMoveableResource(currentResource)
                total_time = self.get_processing_time(currentResource, currentLot)
                currentResource.lastWorkFinishTime = self.T + total_time
                self.appendEvent(self.give_event_number(), currentOperationId, currentLot.lotId, currentResource.resourceId, 'TrackInFinish', self.T, total_time)
                if "DA" in currentResource.resourceId:
                    self.counters.workingDA += 1
                elif "WB" in currentResource.resourceId:
                    self.counters.workingWB += 1
                self.computeIntarget(currentLot)
            else:
                total_time = self.get_processing_time(currentResource, currentLot)
                currentResource.processingTimeInBuffer = total_time
                self.appendEvent(self.give_event_number(), currentOperationId, currentLot.lotId, currentResource.resourceId, 'Waiting', self.T, sys.maxsize)

    def trackInFinish(self, event):
        currentLot = self.info.lotMap[event.lotId]
        assert isinstance(currentLot, Lot)
        if event.resourceId == "MD_RES":
            self.info.eventList.remove(event)
            currentLot.recordHistory('TRACK OUT', self.T, 'WAIT', 'END', '', 'SHIP')
            self.update_confliting_lots(currentLot)
            currentLot.recordHistory('FACTORY OUT', self.T, 'WAIT', 'END', '', '')
            self.KPIs.TATMap[event.lotId] = self.T - currentLot.factoryInTime
            if self.T < currentLot.lotDueDate:
                self.KPIs.completedProductQuantity[currentLot.productId] = self.KPIs.completedProductQuantity[currentLot.productId] + currentLot.lotQuantity
        else:
            currentResource = self.info.resourceMap[event.resourceId]
            assert isinstance(currentResource, Resource)
            nextOperationId = self.info.flowMap[currentLot.flowId].getNowOperation(currentLot.flowNumber + 1)
            currentOperationId = currentLot.currentOperationId

            currentResource.recordHistory('END PROD', self.T, 'IDLE', '', '', '', '')
            operationIdBeforeTrackIn = self.info.flowMap[currentLot.flowId].getNowOperation(currentLot.flowNumber)
            if 'DA' in operationIdBeforeTrackIn:
                currentLot.DA_flow_number += 1
            currentLot.flowNumber += 1
            currentOperationId = self.info.flowMap[currentLot.flowId].getNowOperation(currentLot.flowNumber)
            if currentLot.reservedSameResource:
                currentLot.recordHistory('TRACK OUT', self.T, 'WAIT', currentResource.resourceId, currentResource.resourceId, currentOperationId)
                self.update_confliting_lots(currentLot)
            else:
                currentLot.recordHistory('TRACK OUT', self.T, 'WAIT', 'WAY TO ' + currentOperationId[0:2] + '_STOCK', '', currentOperationId)
                self.update_confliting_lots(currentLot)
            self.trackOutFinish(Event(self.give_event_number(), currentLot.currentOperationId, event.lotId, event.resourceId, 'TrackOutFinish', self.T, 0))

    def trackOutFinish(self, event):
        currentLot = self.info.lotMap[event.lotId]
        assert isinstance(currentLot, Lot)
        currentLot.currentOperationArrivalTime = self.T
        currentLot.currentOperationStartTime = -1
        if currentLot.reservedSameResource:
            self.moveFinish(Event(self.give_event_number(), currentLot.currentOperationId, event.lotId, event.resourceId, 'MoveFinish', self.T, 0))
        else:
            currentLot.recordHistory('MOVE START', self.T, 'MOVE', currentLot.lotLocation, '')
            self.update_confliting_lots(currentLot)
            self.appendEvent(self.give_event_number(), currentLot.currentOperationId, event.lotId, '', 'TrackOutMoveFinish', self.T, self.parameters.moveTime)
            self.updateWIPStatus(event.type, currentLot.currentOperationId, currentLot)
        currentResource = self.info.resourceMap[event.resourceId]

    def trackOutMoveFinish(self, event):
        currentLot = self.info.lotMap[event.lotId]
        assert isinstance(currentLot, Lot)
        toLocationId = currentLot.currentOperationId[0:2] + '_STOCK'
        currentLot.recordHistory('MOVE END', self.T, 'WAIT', toLocationId, "")
        self.update_confliting_lots(currentLot)
        # move end 처리 -> 해당 operation의 stock에 대기 중인 상황 시작
        if currentLot.currentOperationId != 'MD':
            temp_productId = currentLot.productId
            temp_flow_number = int(currentLot.currentOperationId[2:3])
            if type(self.num_of_lot_count_in_stocker[currentLot.currentOperationId[0:2]][temp_productId][temp_flow_number]) == int:
                self.num_of_lot_count_in_stocker[currentLot.currentOperationId[0:2]][temp_productId][temp_flow_number] += currentLot.lotQuantity
            else:
                self.num_of_lot_count_in_stocker[currentLot.currentOperationId[0:2]][temp_productId][temp_flow_number] = currentLot.lotQuantity
        if currentLot.currentOperationId == "MD":
            currentLot.recordHistory('MOVE START', self.T, 'MOVE', 'MD_RES', 'MD_RES')
            self.update_confliting_lots(currentLot)
            self.appendEvent(self.give_event_number(), currentLot.currentOperationId, currentLot.lotId, 'MD_RES', 'MoveFinish', self.T, self.parameters.moveTime)
        # TrackOutMoveFinish에서 이미 예약된 lot은 ReserveMoveWaiting 처리
        elif currentLot.reservedResourceId != "":
            self.appendEvent(self.give_event_number(), currentLot.currentOperationId, event.lotId, '', 'ReserveMoveWaiting', self.T, sys.maxsize)
        else:
            self.appendEvent(self.give_event_number(), currentLot.currentOperationId, event.lotId, '', "MoveWaiting", self.T, sys.maxsize)
        if 'WB' in currentLot.currentOperationId:
            self.check_lot_in_WB_stock[currentLot.productId][currentLot.currentOperationId] += 1
        self.updateWIPStatus(event.type, currentLot.currentOperationId, currentLot)

    def processMoveWaiting(self):
        possible_operation_type = ['DA', 'WB']
        decision_maked = False
        for operation_type in possible_operation_type:
            moveable_res_list = []
            for modelId, resourceList in self.moveableResourceListMap.items():
                if operation_type in modelId:
                    moveable_res_list.extend(resourceList)
            if len(moveable_res_list) == 0:
                continue

            candlot_list = []
            move_candlot_list = []
            wait_candlot_list = []
            working_candlot_list = []
            self.get_candidate_lot_list(operation_type, candlot_list, move_candlot_list, wait_candlot_list, working_candlot_list)

            if len(wait_candlot_list) == 0:
                # stocker 대기 중인 Lot이 없을 때, 예약 의사결정은 불필요하다
                candlot_list.clear()
            if len(moveable_res_list) == 0 or len(candlot_list) == 0:
                continue

            decision_result_list = []
            if operation_type == 'DA':
                decision_result_list = self.getDARTDDecision(moveable_res_list, candlot_list, wait_candlot_list, move_candlot_list, working_candlot_list)
            else:
                decision_result_list = self.getWBDecision(candlot_list, moveable_res_list)
            for decision_string in decision_result_list:
                selectedLot_id = decision_string.split('/')[0]
                if selectedLot_id == '':
                    continue
                selectedLot = self.info.lotMap[selectedLot_id]
                if 'DA' in operation_type:
                    self.count += 1
                decision_maked = True
                assert isinstance(selectedLot, Lot)
                currentOperationId = selectedLot.currentOperationId
                selectedResource = self.info.resourceMap[decision_string.split('/')[1]]
                assert isinstance(selectedResource, Resource)
                if currentOperationId == 'DA1':
                    selectedLot.factoryInTime = self.T
                selectedResource.resourceBuffer.append(selectedLot.lotId)
                self.updateMoveableResource(selectedResource)
                if selectedLot in wait_candlot_list:
                    # stock 대기 중인 Lot이 선택 된 경우
                    if len(selectedLot.historyList) > 0:
                        latestLotHistory = selectedLot.historyList[-1]
                        assert isinstance(latestLotHistory, LotHistory)
                        if selectedLot.currentOperationId == "DA1":
                            self.KPIs.waitingMap[selectedLot.lotId] += self.T - selectedLot.factoryInTime
                            self.selected_status_dict['In_Cst'][int(self.T / (60 * 60 * self.selected_rule_time_unit))] += 1
                        else:
                            self.KPIs.waitingMap[selectedLot.lotId] += self.T - latestLotHistory.eventTime
                            # For count value for state making
                            temp_productId = selectedLot.productId
                            temp_flow_number = int(currentOperationId[2:3])
                            self.selected_status_dict['In_DA'][int(self.T / (60 * 60 * self.selected_rule_time_unit))] += 1
                            if type(self.num_of_lot_count_in_stocker[currentOperationId[0:2]][temp_productId][temp_flow_number]) == int:
                                self.num_of_lot_count_in_stocker[currentOperationId[0:2]][temp_productId][temp_flow_number] -= selectedLot.lotQuantity
                            else:
                                print("Error: this lot is not in the DA Stocker", selectedLot.lotId, currentOperationId)
                    toLocationId = selectedResource.resourceId[0:3] + "BUF" + selectedResource.resourceId[6:]
                    selectedLot.recordHistory('MOVE START', self.T, 'MOVE', toLocationId, selectedResource.resourceId)
                    self.update_confliting_lots(selectedLot)
                    self.updateWIPStatus("MoveWaiting", currentOperationId, selectedLot)
                    self.appendEvent(self.give_event_number(), currentOperationId, selectedLot.lotId, selectedResource.resourceId, 'MoveFinish', self.T, self.parameters.moveTime)
                    wait_candlot_list.remove(selectedLot)
                elif selectedLot in move_candlot_list:
                    # move 중인 Lot이 선택된 상황
                    nextOperationId = self.info.flowMap[selectedLot.flowId].getNowOperation(selectedLot.flowNumber)
                    selectedLot.setReservationRecord(nextOperationId, self.T, selectedResource.resourceId)
                    move_candlot_list.remove(selectedLot)
                    self.selected_status_dict['To_DA'][int(self.T / (60 * 60 * self.selected_rule_time_unit))] += 1
                else:
                    # 작업 중인 Lot이 선택된 상황
                    nextOperationId = self.info.flowMap[selectedLot.flowId].getNowOperation(selectedLot.flowNumber + 1)
                    selectedLot.setReservationRecord(nextOperationId, self.T, selectedResource.resourceId)
                    self.selected_status_dict['WB'][int(self.T / (60 * 60 * self.selected_rule_time_unit))] += 1
                    # Die attach 작업 중에 자신이 작업중이 Lot을 예약하게 된 경우
                    if selectedResource.lotIdProcessed == selectedLot.lotId:
                        selectedLot.reservedSameResource = True

        return decision_maked

    def processWaiting(self, event):
        currentLot = self.info.lotMap[event.lotId]
        assert isinstance(currentLot, Lot)
        currentResourceId = event.resourceId
        currentOperationId = currentLot.currentOperationId

        if event.type == 'Waiting':
            currentResource = self.info.resourceMap[currentResourceId]
            assert isinstance(currentResource, Resource)
            if currentResource.resourceStatus == "IDLE":
                latestLotHistory = currentLot.historyList[-1]
                currentLot.recordHistory("TRACK IN", self.T, "PROCESS", currentResourceId, currentResourceId)
                self.update_confliting_lots(currentLot)
                if "_" not in currentLot.lotId:
                    self.KPIs.waitingMap[currentLot.lotId] += self.T - latestLotHistory.eventTime
                currentResource.recordHistory("START PROD", self.T, "RUN", currentLot.productId, currentLot.lotId,
                                              self.info.flowMap[currentLot.flowId].getNowOperation(currentLot.flowNumber),
                                              self.info.flowMap[currentLot.flowId].getNowOperation(currentLot.flowNumber - 1))
                totalTime = self.get_processing_time(currentResource, currentLot)
                currentResource.lastWorkFinishTime = self.T + totalTime
                currentResource.processingTimeInBuffer = 0
                self.appendEvent(self.give_event_number(), currentOperationId, currentLot.lotId, currentResourceId, 'TrackInFinish', self.T, totalTime)
                self.updateMoveableResource(currentResource)
                if "DA" in currentResourceId:
                    self.counters.workingDA += 1
                elif "WB" in currentResourceId:
                    self.counters.workingWB += 1
                self.computeIntarget(currentLot)
                return True
            else:
                return False
        elif event.type == "MoveWaiting":
            print('wrong way of calling move waiting')
            return False
        elif event.type == 'ReserveMoveWaiting': #예약대기
            if "DA" in currentLot.reservedResourceId or "WB" in currentLot.reservedResourceId:
                reservedResource = self.info.resourceMap[currentLot.reservedResourceId]
                assert isinstance(reservedResource, Resource)
                # buffer 비는 것 check
                if len(reservedResource.resourceBuffer) == reservedResource.bufferSize and reservedResource.resourceBuffer[0] != currentLot.lotId:
                    return False
                if len(reservedResource.resourceBuffer) == 0:
                    reservedResource.resourceBuffer.append(currentLot.lotId)
                    toLocationId = reservedResource.resourceId[0:3] + 'BUF' + reservedResource.resourceId[6:]
                    currentLot.recordHistory('MOVE START', self.T, 'MOVE', toLocationId, reservedResource.resourceId)
                    self.update_confliting_lots(currentLot)
                    self.updateMoveableResource(reservedResource)
                    self.updateWIPStatus(event.type, currentOperationId, currentLot)
                    self.appendEvent(self.give_event_number(), currentOperationId, currentLot.lotId, reservedResource.resourceId, 'MoveFinish', self.T, self.parameters.moveTime)
                    temp_productId = currentLot.productId
                    temp_flow_number = int(currentLot.currentOperationId[2:3])
                    if type(self.num_of_lot_count_in_stocker[currentLot.currentOperationId[0:2]][temp_productId][temp_flow_number]) == int:
                        self.num_of_lot_count_in_stocker[currentLot.currentOperationId[0:2]][temp_productId][temp_flow_number] -= currentLot.lotQuantity
                    else:
                        print("Error: this lot is not in the WB Stocker", currentLot.lotId, currentOperationId)
                    return True
                else:
                    toLocationId = reservedResource.resourceId[0:3] + 'BUF' + reservedResource.resourceId[6:]
                    currentLot.recordHistory('MOVE START', self.T, 'MOVE', toLocationId, reservedResource.resourceId)
                    self.update_confliting_lots(currentLot)
                    self.updateWIPStatus(event.type, currentOperationId, currentLot)
                    self.appendEvent(self.give_event_number(), currentOperationId, currentLot.lotId, reservedResource.resourceId, 'MoveFinish', self.T, self.parameters.moveTime)
                    temp_productId = currentLot.productId
                    temp_flow_number = int(currentLot.currentOperationId[2:3])
                    if type(self.num_of_lot_count_in_stocker[currentLot.currentOperationId[0:2]][temp_productId][temp_flow_number]) == int:
                        self.num_of_lot_count_in_stocker[currentLot.currentOperationId[0:2]][temp_productId][temp_flow_number] -= currentLot.lotQuantity
                    else:
                        print("Error: this lot is not in the DA Stocker", currentLot.lotId, currentOperationId)
                    return True
        else:
            return False

    def initialize(self):
        self.T = 0
        self.info.eventList.sort(key=lambda x: (x.start_time + x.period_time, x.lotId))
        for res_id, _ in self.info.resourceMap.items():
            if 'DA' in res_id:
                self.num_of_resource_per_op['DA'] += 1
            else:
                self.num_of_resource_per_op['WB'] += 1

        WIP_intarget = defaultdict(lambda: defaultdict(int))
        for currentLotId, currentLot in self.info.lotMap.items():
            currentOperationId = self.info.flowMap.get(currentLot.flowId).getNowOperation(currentLot.flowNumber)
            currentOperationName = currentOperationId[0:2]
            location = currentLot.lotLocation
            assert isinstance(currentLot, Lot)
            # For state making (progress rate)
            self.counters.total_lot_per_product[currentLot.productId] += currentLot.lotQuantity
            # For WIP levels per product
            if type(self.counters.WIP_level_per_product[currentLot.productId][currentOperationName][currentOperationId]) == int:
                self.counters.WIP_level_per_product[currentLot.productId][currentOperationName][currentOperationId] += 1
                self.WIP_level_per_T_product[currentLot.productId][currentOperationName][currentOperationId][self.T] += 1
            else:
                self.counters.WIP_level_per_product[currentLot.productId][currentOperationName][currentOperationId] = 1
                self.WIP_level_per_T_product[currentLot.productId][currentOperationName][currentOperationId][self.T] = 1
            if currentOperationId != 'DA1':
                if type(self.counters.WIP_level_per_product_agg[currentLot.productId][currentOperationName]) == int:
                    self.counters.WIP_level_per_product_agg[currentLot.productId][currentOperationName] += 1
                    self.WIP_level_per_T_product_agg[currentLot.productId][currentOperationName][self.T] += 1
                else:
                    self.counters.WIP_level_per_product_agg[currentLot.productId][currentOperationName] = 1
                    self.WIP_level_per_T_product_agg[currentLot.productId][currentOperationName][self.T] = 1

                self.counters.WIP_level_per_operation[currentOperationName] += 1
                self.WIP_level_per_T_operation[currentOperationName][self.T] += 1

            if "STOCK" in location:
                if "CST" in location:
                    currentLot.recordHistory("FACTORY IN", self.T, "WAIT", "CST_STOCK", "", "DA1", None)
                    if currentLot.factoryInTime > -1:
                        self.appendEvent(self.give_event_number(), currentOperationId, currentLotId, "", "FactoryInFinish", currentLot.factoryInTime, 0)
                else:
                    currentLot.recordHistory("MOVE END", self.T, "WAIT", location, currentLot.currentResourceId, currentOperationId, currentLot.motherLot)
                if "_" in currentLotId:
                    self.processMerge(currentLot)  # Merge 중인 300초 동안에 저장된 WIP일 경우 다시 수행해 줄 필요가 있음
                else:
                    if currentLot.factoryInTime < self.T:
                        self.appendEvent(self.give_event_number(), currentOperationId, currentLotId, "", "MoveWaiting", self.T, sys.maxsize)
                if 'DA' in location:
                    # For count value for state making
                    temp_productId = currentLot.productId
                    temp_flow_number = int(currentLot.currentOperationId[2:3])
                    if type(self.num_of_lot_count_in_stocker['DA'][temp_productId][temp_flow_number]) == int:
                        self.num_of_lot_count_in_stocker['DA'][temp_productId][temp_flow_number] += currentLot.lotQuantity
                    else:
                        self.num_of_lot_count_in_stocker['DA'][temp_productId][temp_flow_number] = currentLot.lotQuantity

        for resourceId, currentResource in self.info.resourceMap.items():
            resourceModelId = currentResource.resourceModelId
            self.existResourceIdMap[resourceModelId].append(resourceId)
            # initialize feasibility map
            if len(currentResource.resourceBuffer) < currentResource.bufferSize:
                self.moveableResourceListMap[resourceModelId].append(currentResource)
            # For DA Selection
            tempResourceModel = self.info.resourceModelMap[currentResource.resourceModelId]
            currentResource.numOfPossibleProductType = len(tempResourceModel.resourceArrangementMap)

        for _, currentLot in self.info.lotMap.items():
            product_type = currentLot.productId
            self.totalLotPerProduct[product_type] += 1
            loc = currentLot.lotLocation
            if len(currentLot.subLotIdList) > 0:  # mother lot 무시
                continue
            if 'WAY TO' in loc:
                self.counters.mgzMoveCount += 1
            elif 'STOCK' in loc:
                if 'CST' in loc or 'MD' in loc or currentLot.factoryInTime < 0:
                    continue
                self.counters.mgzCount += 1
                if 'DA' in loc:
                    self.counters.mgzDACount += 1

        # self.updateWIPPerTime(currentLot)
        # For State
        self.conflict_status_init()
        move_waiting = True
        while move_waiting:
            move_waiting = self.processMoveWaiting()
        self.temporary_conflict_state = defaultdict(lambda: defaultdict(list))
        self.info.eventList.sort(key=lambda x: (x.start_time + x.period_time, x.lotId))

    def lot_resource_matching(self, moveableResourceList, SelectionCandidateLotList, operationType,  RTDPolicy):
        decision_Result = []
        if RTDPolicy == 'learner':
            if self.info.needStateNormalization or self.info.needScoreNormalization:
                print(''' ERROR!! Need Normalization!!!! Can not conduct decision using learner''')
            else:
                decision_Result = self.lot_resource_matching_without_setupchange(moveableResourceList, SelectionCandidateLotList, operationType)
        else:
            decision_Result = self.rule_lot_resource_matching_without_setupchange(moveableResourceList, SelectionCandidateLotList, operationType, RTDPolicy)

        return decision_Result

    def getDARTDDecision(self, moveableDAResourceList, candlot_list, wait_candlot_list, move_candlot_list, working_candlot_list):
        decision_result = []
        if self.parameters.DARTDPolicy == 'random':
            rand_num = random.uniform(0, 1)
            if rand_num <= self.intentional_delay_level:
                decision_result = self.lot_resource_matching(moveableDAResourceList, candlot_list, 'DA', self.parameters.DARTDPolicy)
            elif rand_num > self.intentional_delay_level and (len(move_candlot_list) > 0 or len(working_candlot_list) > 0):
                temp_list = []
                temp_list.extend(move_candlot_list)
                temp_list.extend(working_candlot_list)
                decision_result = self.lot_resource_matching(moveableDAResourceList, temp_list, 'DA', self.parameters.DARTDPolicy)
            else:
                decision_result = self.lot_resource_matching(moveableDAResourceList, candlot_list, 'DA', self.parameters.DARTDPolicy)
            if self.parameters.rtdTraining:
                for decision_string in decision_result:
                    if decision_string.split('/')[0] == '':
                        continue
                    selectedLot = self.info.lotMap[decision_string.split('/')[0]]
                    selectedResource = self.info.resourceMap[decision_string.split('/')[1]]
                    assignment_vector = self.get_paper_state_for_bottleneck(selectedLot, selectedResource, 'DA', 'WB')
                    if self.info.needStateNormalization:
                        # 여러 번의 시뮬레이션에서 모두 data를 저장하기 위해서
                        self.original_info.state_nor.append_state(assignment_vector)
                    else:
                        if self.parameters.normalization:
                            normalized_vector = self.original_info.state_nor.normalize(assignment_vector)
                            self.rtd_rec.addInstance(normalized_vector, selectedLot.lotId, selectedResource.resourceId, self.get_operationId_forReserve(selectedLot, 'DA'), self.T)
                        else:
                            self.rtd_rec.addInstance(assignment_vector, selectedLot.lotId, selectedResource.resourceId, self.get_operationId_forReserve(selectedLot, 'DA'), self.T)
        else:
            decision_result = self.lot_resource_matching(moveableDAResourceList, candlot_list, 'DA', self.parameters.DARTDPolicy)

        return decision_result

    def getWBDecision(self, WBSelectionCandidateLotList: "List of Lots (not List of LotIds)", moveableWBResourceList: "List of Resources (not List of ResourceIds)"):
        decisionResult = {}
        decision_result = []
        WBDispatchPolicy = self.parameters.WBRTDPolicy
        decision_result = self.lot_resource_matching(moveableWBResourceList, WBSelectionCandidateLotList,'WB',WBDispatchPolicy)
        # 실질적인 lot-res matching 결과가 있을경우
        if decision_result[0].split('/')[0] != '':
            decisionResult['lot'] = self.info.lotMap[decision_result[0].split('/')[0]]
            decisionResult['resource'] = self.info.resourceMap[decision_result[0].split('/')[1]]
        else:
            decisionResult['lot'] = ''
            decisionResult['resource'] = self.info.resourceMap[decision_result[0].split('/')[1]]

        if self.for_normalization and WBDispatchPolicy == 'random':
            _, new_state_rtd = self.get_snapshot_state()
        return decision_result

    def get_candidate_lot_list(self, operation_type, candlot_list, move_candlot_list, wait_candlot_list, working_candlot_list):
        self.DA_stock_waiting_per_product_id = defaultdict(int)
        if operation_type == 'DA':
            for _, tempLot in self.info.lotMap.items():
                assert isinstance(tempLot, Lot)
                if tempLot.factoryInTime >= self.T:
                    continue
                if tempLot.reservedResourceId != '':
                    continue  # 이미 갈 곳이 정해진 Lot은 중복되지 않도록
                if tempLot.lotStatus == 'WAIT':  # STOCK에서 대기 중인 일반적인 Candidate
                    if tempLot.lotLocation == operation_type + "_STOCK" or tempLot.lotLocation == "CST_STOCK":
                        current_simul_day = int(self.T / self.parameters.UTILCUTTIME) + 1  # DB에 있는 Simulation Day는 1부터 시작
                        candlot_list.append(tempLot)
                        wait_candlot_list.append(tempLot)
                        if tempLot.lotLocation == 'CST_STOCK':
                            pass
                        else:
                            self.DA_stock_waiting_per_product_id[tempLot.productId] += 1
                # 이동 중인 Lot Check
                elif tempLot.lotLocation == 'WAY TO ' + operation_type + '_STOCK' and tempLot.lotStatus == 'MOVE':
                    # Do nothing learner On/Off 가능
                    candlot_list.append(tempLot)
                    move_candlot_list.append(tempLot)
                    # pass
                # 작업 중인 Lot Check (Merge??)
                elif (tempLot.lotStatus == 'PROCESS' and 'DA' in self.info.flowMap[tempLot.flowId].getNowOperation(
                            tempLot.flowNumber + 1)) or (tempLot.lotStatus == 'RUN' and 'DA' in tempLot.currentOperationId):
                    candlot_list.append(tempLot)
                    working_candlot_list.append(tempLot)
                    # pass

        elif operation_type == 'WB':
            for _, tempLot in self.info.lotMap.items():
                if tempLot.reservedResourceId != '':
                    continue
                if tempLot.lotLocation == operation_type + "_STOCK":  # 우선 그냥 대기중인 것만
                    candlot_list.append(tempLot)
                    wait_candlot_list.append(tempLot)
                elif tempLot.lotLocation == 'WAY TO ' + operation_type + '_STOCK' and tempLot.lotStatus == 'MOVE':
                    move_candlot_list.append(tempLot)
                elif tempLot.lotStatus == 'PROCESS' and operation_type in self.info.flowMap[tempLot.flowId].getNowOperation(tempLot.flowNumber + 1):
                    working_candlot_list.append(tempLot)

    def lot_resource_matching_without_setupchange(self, moveableResourceList, SelectionCandidateLotList, OperationType):
        lotResourceListForSecondLearner = []
        input_vector_batch = []
        DA_stock_waiting_time = []
        decision_result_list = []
        for moveable_resource in moveableResourceList:
            currentResourceModel = self.info.resourceModelMap[moveable_resource.resourceModelId]
            for temp_lot in SelectionCandidateLotList:
                candidate_bool = False
                if temp_lot.productId in currentResourceModel.resourceArrangementMap:
                    operationId = self.get_operationId_forReserve(temp_lot, OperationType)
                    if operationId in currentResourceModel.resourceArrangementMap[temp_lot.productId]:
                        candidate_bool = True

                if candidate_bool:
                    assignment_vector = self.get_paper_state_for_bottleneck(temp_lot, moveable_resource, 'DA', 'WB')
                    if temp_lot.lotLocation == 'DA_STOCK':
                        waiting_time_in_DA = self.T - temp_lot.historyList[-1].eventTime
                        DA_stock_waiting_time.append(waiting_time_in_DA)
                    else:
                        DA_stock_waiting_time.append(0)
                    normalized_vector = self.original_info.state_nor.normalize(assignment_vector)
                    input_vector_batch.append(normalized_vector)
                    lotResourceListForSecondLearner.append(temp_lot.lotId + '/' + moveable_resource.resourceId)

        if len(input_vector_batch) > 0:
            normalized_DA_waiting = self.original_info.DA_score_nor.normalize(DA_stock_waiting_time)
            if OperationType == 'DA':
                waiting_output = self.DA_waiting_learner.predict(input_vector_batch)
                if self.DA_idle_learner is not None:
                    idle_output = self.DA_idle_learner.predict(input_vector_batch)
            else:
                waiting_output = self.WB_waiting_learner.predict(input_vector_batch)
            if OperationType == 'DA':
                waiting_output = np.squeeze(waiting_output)
                if self.DA_idle_learner is None:
                    loss_time = waiting_output
                else:
                    idle_output = np.squeeze(idle_output)
                    # loss_time = self.parameters.waiting_weight * waiting_output + self.parameters.idle_weight * idle_output
                    loss_time = self.parameters.waiting_weight * waiting_output + self.parameters.idle_weight * idle_output + self.parameters.DA_waiting_weight * normalized_DA_waiting
                idxs = np.argsort(-loss_time)
                sorted_preference_list = []
                decision_number = self.give_decision_number()
                if len(idxs) == 1:
                    name = lotResourceListForSecondLearner[0]
                    sorted_preference_list.append(name)
                    lot_id_for_view = name.split('/')[0]
                    resource_id_for_view = name.split('/')[1]
                    selectedLot = self.info.lotMap[lot_id_for_view]
                    selectedResource = self.info.resourceMap[resource_id_for_view]
                    if self.DA_idle_learner is None:
                        w_score = 0.0
                        i_score = 0.0
                    else:
                        w_score = waiting_output
                        i_score = idle_output
                    l_score = loss_time
                    self.appendCandidateForViewer(decision_number, selectedLot, selectedResource, w_score, i_score, normalized_DA_waiting, l_score)
                else:
                    for idx in idxs:
                        name = lotResourceListForSecondLearner[idx]
                        sorted_preference_list.append(name)
                        lot_id_for_view = name.split('/')[0]
                        resource_id_for_view = name.split('/')[1]
                        selectedLot = self.info.lotMap[lot_id_for_view]
                        selectedResource = self.info.resourceMap[resource_id_for_view]
                        if self.DA_idle_learner is None:
                            w_score = 0.0
                            i_score = 0.0
                        else:
                            w_score = waiting_output[idx]
                            i_score = idle_output[idx]
                        l_score = loss_time[idx]
                        d_waiting = normalized_DA_waiting[idx]
                        self.appendCandidateForViewer(decision_number, selectedLot, selectedResource, w_score, i_score, d_waiting, l_score)

                resource_id_check_list = []
                lot_id_check_list = []
                """
                순서대로 정렬하여 값이 작은 것부터 순서대로 체크
                lot_id와 resource_id가 모두 앞에 결정된 매칭과 중복 되지 않을 때만 tuple_list에 저장
                """
                for name in sorted_preference_list:
                    temp_lot_id = name.split('/')[0]
                    temp_resource_id = name.split('/')[1]
                    if temp_resource_id not in resource_id_check_list and temp_lot_id not in lot_id_check_list:
                        decision_result_list.append(name)
                        lot_id_check_list.append(temp_lot_id)
                        resource_id_check_list.append(temp_resource_id)

                return decision_result_list
        else:
            if OperationType == 'WB':
                selectedResource = random.choice(moveableResourceList)
                lot_resource_matching = '' + '/' + selectedResource.resourceId
                decision_result_list.append(lot_resource_matching)
            return decision_result_list

    def rule_lot_resource_matching_without_setupchange(self, moveableResourceList, SelectionCandidateLotList, OperationType, RuleType):
        decision_result = []
        if len(moveableResourceList) > 0:
            feasible_moveableResourceList = []
            candidateLotListForResource = []
            for selected_resource in moveableResourceList:
                feasible = False
                currentResourceModel = self.info.resourceModelMap[selected_resource.resourceModelId]
                assert isinstance(currentResourceModel, ResourceModel)
                for tempLot in SelectionCandidateLotList:
                    if tempLot.productId in currentResourceModel.resourceArrangementMap:
                        if self.get_operationId_forReserve(tempLot, OperationType) in currentResourceModel.resourceArrangementMap[tempLot.productId]:
                            feasible = True
                            break
                if feasible:
                    feasible_moveableResourceList.append(selected_resource)

            if len(feasible_moveableResourceList) > 0:
                selectedResource = self.res_choice(feasible_moveableResourceList, RuleType)
                currentResourceModel = self.info.resourceModelMap[selectedResource.resourceModelId]
                assert isinstance(currentResourceModel, ResourceModel)
                for tempLot in SelectionCandidateLotList:
                    if tempLot.productId in currentResourceModel.resourceArrangementMap:
                        if self.get_operationId_forReserve(tempLot, OperationType) in currentResourceModel.resourceArrangementMap[tempLot.productId]:
                            candidateLotListForResource.append(tempLot)

            else:
                selectedResource = random.choice(moveableResourceList)
                lot_resource_matching = '' + '/' + selectedResource.resourceId
                decision_result.append(lot_resource_matching)
                return decision_result

            if len(candidateLotListForResource) > 0:
                selectedLot = self.lot_choice(candidateLotListForResource, RuleType, selectedResource)
                lot_resource_matching = selectedLot.lotId + '/' + selectedResource.resourceId
                decision_number = self.give_decision_number()
                self.appendCandidateForViewer(decision_number, selectedLot, selectedResource, 0, 0, 0, 0)
                decision_result.append(lot_resource_matching)
                # self.appendCandidateForViewer(selectedLot, selected_resource, 0)
            else:
                lot_resource_matching = '' + '/' + selectedResource.resourceId
                decision_result.append(lot_resource_matching)

        return decision_result

    def computeIntarget(self, selectedLot):
        current_simul_day = int(self.T / self.parameters.UTILCUTTIME)
        if selectedLot.currentOperationId == "DA1":
            self.counters.InputCount[self.T] = self.counters.inputCounter
            self.counters.inputCounter += 1
            if self.T <= self.parameters.UTILCUTTIME * (self.info.simulDay):
                self.counters.inTargetCount[self.T] = self.counters.inTargetCounter
                self.counters.inTargetCounter += 1
            # self.counters.inTargetCompletion[current_simul_day][selectedLot.productId] += selectedLot.lotQuantity
            self.counters.inTargetCompletion[current_simul_day][selectedLot.productId] += 1
            self.counters.cumulativeInTargetCompletion[selectedLot.productId] += selectedLot.lotQuantity
            self.counters.inTargetCountByProduct[selectedLot.productId][self.T] = self.counters.inTargetCompletion[current_simul_day][selectedLot.productId]


