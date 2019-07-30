import simulator.simRecord as simRecord
from simulator.simRecord import *
import problemIO.problem as pro
from problemIO.resource import *
from problemIO.lot import *
from problemIO.product import *
from collections import defaultdict
from collections import OrderedDict
import time
from datetime import datetime
import os
import json
import numpy as np
from simulator.simParameter import *


class JSimUtil(object):
    def __init__(self, sim_parameter):
        # time check 관련
        self.clock = 0
        self.start_time = time.time()

        # print(datetime.fromtimestamp(self.start_time).strftime('%Y-%m-%d %H:%M'))
        self.T = 0
        self.moveableResourceListMap = defaultdict(list)
        self.existResourceIdMap = defaultdict(list)
        self.parameters = sim_parameter
        self.rtd_rec = simRecord.DispatchingRecords(self.parameters.trainingFileName, ',')
        self.counters = simRecord.Counter()
        self.KPIs = simRecord.KPIs()
        self.sr = simRecord.SolutionResult()
        self.ganttChart = simRecord.GanttChart()
        self.info = pro.ProductionInfo()
        self.UTILCUTTIME = 0
        self.giveEventId = 0
        self.decisionId = 0
        self.waitingEventList = []
        self.decisionList = []
        self.production_load = defaultdict(lambda: defaultdict(list))
        self.resModelState = {}
        self.sameLotCount = defaultdict(int)
        self.num_of_resource_per_op = defaultdict(int)
        nested_dict = lambda: defaultdict(nested_dict)
        self.totalLotPerProduct = defaultdict(int)
        """ For Dispatching rules """
        self.check_lot_in_WB_stock = defaultdict(lambda: defaultdict(int))

        """ For Score Calculate """
        self.DA_stock_waiting_per_product_id = defaultdict(int)

        """ For Make State """
        self.num_of_lot_count_in_stocker = nested_dict()
        self.conflict_dict = defaultdict(lambda: defaultdict(set))  # First key: product id, Second key: operation id
        self.feasible_resource_list_per_product_oper = defaultdict(lambda: defaultdict(list))
        self.conflict_lot_location = defaultdict(lambda: defaultdict(int))  # First key: product id/operation id, Second key: location
        self.lot_count_per_loc = defaultdict(int)  # First key: resource_model Second key: location
        self.temporary_conflict_state = defaultdict(lambda: defaultdict(list))
        self.loc_names_for_state_making = [
                                    '/FACTORY IN/CST_S',
                                    'FACTORY IN/MOVE START/DA_BU',
                                    'MOVE END/MOVE START/DA_BU' ,
                                    'MOVE END/MOVE START/MD_RE',
                                    'MOVE END/MOVE START/WB_BU',
                                    'MOVE END/TRACK IN/DA_RE',
                                    'MOVE END/TRACK IN/MD_RE',
                                    'MOVE END/TRACK IN/WB_RE',
                                    'MOVE START/MOVE END/DA_BU',
                                    'MOVE START/MOVE END/DA_ST',
                                    # 'MOVE START/MOVE END/MD_RE',
                                    # 'MOVE START/MOVE END/MD_ST',
                                    'MOVE START/MOVE END/WB_BU',
                                    'MOVE START/MOVE END/WB_ST',
                                    # 'TRACK IN/TRACK OUT/DA_ST',
                                    # 'TRACK IN/TRACK OUT/END',
                                    # 'TRACK IN/TRACK OUT/MD_ST',
                                    # 'TRACK IN/TRACK OUT/WB_ST',
                                    'TRACK OUT/MOVE START/DA_ST',
                                    'TRACK OUT/MOVE START/MD_ST',
                                    'TRACK OUT/MOVE START/WB_ST'
                            ]

        """ For viewer """
        self.WIP_level_per_T_product = nested_dict()
        self.WIP_level_per_T_product_agg = nested_dict()
        self.WIP_level_per_T_operation = defaultdict(lambda: defaultdict(int))
        self.best_EQP_per_T_product = nested_dict()
        self.conducted_setup_record = defaultdict(list)

        """ For exp """
        self.WBUtilPerTime = {}
        self.selected_status_dict = defaultdict(lambda: defaultdict(int))
        self.cst_dec = [0] * 35
        self.DA_dec = [0] * 35
        self.move_dec = [0] * 35
        self.processing_dec = [0] * 35

        """ For Rule Learner """
        self.selected_rule_dict = defaultdict(lambda: defaultdict(int))
        self.selected_rule_time_unit = 3

    def setSimClock(self, clock):
        self.clock = clock

    def give_event_number(self):
        self.giveEventId += 1
        return self.giveEventId

    def give_decision_number(self):
        self.decisionId += 1
        return self.decisionId

    def get_processing_time(self, currentResource: "Resource", currentLot: "Lot"):
        resourceModel = self.info.resourceModelMap[currentResource.resourceModelId]
        assert isinstance(resourceModel, ResourceModel)
        resourceArrangement = resourceModel.resourceArrangementMap[currentLot.productId][currentLot.currentOperationId]
        assert isinstance(resourceArrangement, ResourceArrangement)
        processingUnit = resourceArrangement.processingUnit
        processingTime = resourceArrangement.processingTime
        calculatedTime = 0
        if processingUnit == "EA":
            calculatedTime = processingTime * currentLot.lotQuantity
        else:
            calculatedTime = processingTime
        if "DA" in currentLot.currentOperationId:
            calculatedTime *= self.info.DASTRatio
        elif "WB" in currentLot.currentOperationId:
            calculatedTime *= self.info.WBSTRatio
        # totalTime = lotLoadingTime + lotUnLoadingTime + calculatedTime  # Capa 비교때문에 loading, unloading 일단 제외
        totalTime = calculatedTime
        return totalTime

    def updateMoveableResource(self, currentResource: "Resource"):
        currentResourceModelId = currentResource.resourceModelId
        if len(currentResource.resourceBuffer) >= currentResource.bufferSize:
            self.moveableResourceListMap[currentResourceModelId].remove(currentResource)
        else:
            self.moveableResourceListMap[currentResourceModelId].append(currentResource)

    def updateWIPStatus(self, event_type, currentOperationId, currentLot):
        if currentOperationId == "MD" or currentOperationId == "DA1":
            return
        flowNumber = currentLot.flowNumber
        flowId = currentLot.flowId
        nowOper = self.info.flowMap[flowId].operationSequence[flowNumber]
        currentOperationName = nowOper[0:2]
        if event_type == 'MoveWaiting':
            self.counters.mgzCount -= 1
            if "DA" in currentOperationId:
                self.counters.mgzDACount -= 1
            # 1개도 없을리가 없으므로 이렇게만 처리 해도 될 듯함
            self.counters.WIP_level_per_product[currentLot.productId][currentOperationName][nowOper] -= 1
            self.counters.WIP_level_per_product_agg[currentLot.productId][currentOperationName] -= 1
            self.counters.WIP_level_per_operation[currentOperationName] -= 1
        elif event_type == 'TrackOutMoveFinish':
            self.counters.mgzMoveCount -= 1
            self.counters.mgzCount += 1
            if "DA" in currentOperationId:
                self.counters.mgzDACount += 1

            if type(self.counters.WIP_level_per_product[currentLot.productId][currentOperationName][nowOper]) == int:
                self.counters.WIP_level_per_product[currentLot.productId][currentOperationName][nowOper] += 1
            else:
                self.counters.WIP_level_per_product[currentLot.productId][currentOperationName][nowOper] = 1
            if type(self.counters.WIP_level_per_product_agg[currentLot.productId][currentOperationName]) == int:
                self.counters.WIP_level_per_product_agg[currentLot.productId][currentOperationName] += 1
            else:
                self.counters.WIP_level_per_product_agg[currentLot.productId][currentOperationName] = 1
            self.counters.WIP_level_per_operation[currentOperationName] += 1
        elif event_type == 'TrackOutFinish':
            self.counters.mgzMoveCount += 1
        elif event_type == 'ReserveMoveWaiting':
            self.counters.mgzCount -= 1
            if "DA" in currentOperationId:
                self.counters.mgzDACount -= 1
            # 1개도 없을리가 없으므로 이렇게만 처리 해도 될 듯함
            self.counters.WIP_level_per_product[currentLot.productId][currentOperationName][nowOper] -= 1
            self.counters.WIP_level_per_product_agg[currentLot.productId][currentOperationName] -= 1
            self.counters.WIP_level_per_operation[currentOperationName] -= 1
        else:
            print("ERROR!! inappropriate Event type for WIP Change", type)
        if event_type != 'MergeWaiting':
            # print(type, " ", self.counters.mgzCount, " ", self.counters.mgzDACount)
            self.updateWIPPerTime(currentLot)

    def appendEvent(self, giveEventId, operationId, lotId, resourceId, type, startT, periodT):
        currentEvent = Event(giveEventId, operationId, lotId, resourceId, type, startT, periodT)
        self.info.eventList.append(currentEvent)
        if type == 'SetupChangeFinish' or type == 'CallRTS' or type == 'UpdateRewardInfo' or type == 'UpdateMoveableResList':
            return
        currentLot = self.info.lotMap[lotId]
        assert isinstance(currentLot, Lot)
        self.removeEvent(currentLot.nowEvent)
        if "Waiting" in currentEvent.type and currentEvent.type != "MoveWaiting":
            self.waitingEventList.append(currentEvent)
        currentLot.nowEvent = currentEvent

    def appendCandidateForViewer(self, decision_number, selectedLot, selectedResource, waiting, idle, d_waiting, loss, rule=''):
        realOperationId = selectedLot.currentOperationId
        CSTBufferCount = 0
        for lotId, currentLot in self.info.lotMap.items():
            if currentLot.lotLocation == "CST_STOCK":
                CSTBufferCount += 1

        if selectedLot.lotStatus == "PROCESS" or 'WB' in selectedLot.lotLocation:  # 작업 중인 Lot
            selectedLot.currentOperationId = self.info.flowMap[selectedLot.flowId].getNowOperation(selectedLot.flowNumber + 1)
        assert isinstance(selectedLot, Lot)
        if rule == '':
            currentDecision = decisionViewer(decision_number, self.T, "DA", selectedLot.lotId,
                                             selectedLot.lotStatus,
                                             selectedResource.resourceId + "-" + selectedLot.lotId,
                                             selectedLot.currentOperationId,
                                             selectedLot.productId, selectedLot.lotQuantity, self.counters.mgzCount,
                                             self.counters.mgzDACount, self.counters.mgzCount - self.counters.mgzDACount,
                                             self.counters.workingDA,
                                             self.counters.workingWB, self.counters.inputCounter, self.counters.shipCounter,
                                             CSTBufferCount, selectedLot.flowId, selectedLot.lotLocation, waiting, idle, d_waiting, loss)
        else:
            currentDecision = decisionViewer(decision_number, self.T, "DA", selectedLot.lotId,
                                             selectedLot.lotStatus,
                                             selectedResource.resourceId + "-" + rule,
                                             selectedLot.currentOperationId,
                                             selectedLot.productId, selectedLot.lotQuantity, self.counters.mgzCount,
                                             self.counters.mgzDACount,
                                             self.counters.mgzCount - self.counters.mgzDACount,
                                             self.counters.workingDA,
                                             self.counters.workingWB, self.counters.inputCounter,
                                             self.counters.shipCounter,
                                             CSTBufferCount, selectedLot.flowId, selectedLot.lotLocation, waiting, idle, d_waiting, loss)
        self.decisionList.append(currentDecision)
        selectedLot.currentOperationId = realOperationId

    def updateWIPPerTime(self, currentLot):
        self.counters.WIPLevel[self.T] = self.counters.mgzCount
        self.counters.daWIPLevel[self.T] = self.counters.mgzDACount
        self.counters.wbWIPLevel[self.T] = self.counters.mgzCount - self.counters.mgzDACount

        flowNumber = currentLot.flowNumber
        flowId = currentLot.flowId
        nowOper = self.info.flowMap[flowId].operationSequence[flowNumber]
        currentOperationName = nowOper[0:2]

        if type(self.counters.WIP_level_per_product[currentLot.productId][currentOperationName][nowOper]) == int:
            self.WIP_level_per_T_product[currentLot.productId][currentOperationName][nowOper][self.T] = \
                self.counters.WIP_level_per_product[currentLot.productId][currentOperationName][nowOper]
        else:
            self.WIP_level_per_T_product[currentLot.productId][currentOperationName][nowOper][self.T] = 0

        if type(self.counters.WIP_level_per_product_agg[currentLot.productId][currentOperationName]) == int:
            self.WIP_level_per_T_product_agg[currentLot.productId][currentOperationName][self.T] = \
                self.counters.WIP_level_per_product_agg[currentLot.productId][currentOperationName]
        else:
            self.WIP_level_per_T_product_agg[currentLot.productId][currentOperationName][self.T] = 0

        self.WIP_level_per_T_operation[currentOperationName][self.T] = self.counters.WIP_level_per_operation[
            currentOperationName]

    def removeEvent(self, event):
        if event in self.info.eventList:
            del self.info.eventList[self.info.eventList.index(event)]
            self.info.lotMap[event.lotId].nowEvent = None
            if event in self.waitingEventList:
                del self.waitingEventList[self.waitingEventList.index(event)]

    def write_lot_history(self):
        project_route = os.getcwd()
        if not os.path.exists(os.path.join(project_route, 'history')):
            os.makedirs(os.path.join(project_route, 'history'))
        path_lot = os.path.join(project_route, 'history', '_lot_history.txt')
        with open(path_lot, 'w+') as write_history:
            write_history.write('LOT ID\tPRODUCT ID\tOPERATION ID\tQUANTITY\tLOSS QUANTITY\tUOM of QUANTITY\t'
                                + 'FROM EVENT\tEVENT\tEVENT TIME\tDURATION\tFROM STATUS\tTO STATUS\tFROM OPERATION\tTO OPERATION\t'
                                + 'TO LOCATION ID\tTO RESOURCE ID\tMOTHER LOT ID\n')
            for lotId in sorted(self.info.lotMap.keys()):
                currentLot = self.info.lotMap[lotId]
                assert isinstance(currentLot, Lot)
                productId = currentLot.productId
                currentLot.historyList.sort(key=lambda x: x.eventTime)
                for lot_history in currentLot.historyList:
                    assert isinstance(lot_history, LotHistory)
                    event_time = datetime.fromtimestamp(self.start_time + lot_history.eventTime).strftime(
                        '%Y-%m-%d %H:%M')
                    write_history.write(
                        lot_history.lotId + "\t" + lot_history.productId + "\t" + lot_history.operationId + "\t"
                        + str(lot_history.quantity) + "\t" + str(
                            lot_history.lossQuantity) + "\t" + lot_history.UOMofQuantity
                        + "\t" + lot_history.fromEvent + "\t" + lot_history.event + "\t" + event_time + "\t"
                        + str(lot_history.duration) + "\t" + lot_history.fromStatus + "\t" + lot_history.toStatus + "\t"
                        + lot_history.fromOperationId + "\t" + lot_history.toOperationId + "\t"
                        + lot_history.toLocationId + "\t" + lot_history.toResourceId + "\t" + lot_history.motherLotId + "\n")

        path_resource = os.path.join(project_route, 'history', '_resource_history.txt')
        with open(path_resource, 'w+') as write_history:
            write_history.write('RESOURCE ID\tFROM EVENT\tEVENT\tEVENT TIME\tDURATION\tFROM STATUS\tTO STATUS\t'
                                + 'OPERATION ID\tLot Prior Operation ID\tPRODUCT ID PROCESSED\tLOT ID PROCESSED\n')
            for resourceId in sorted(self.info.resourceMap.keys()):
                resourceHistoryList = self.info.resourceMap[resourceId].historyList
                resourceHistoryList.sort(key=lambda x: x.eventTime)
                for resource_history in resourceHistoryList:
                    event_time = datetime.fromtimestamp(self.start_time + resource_history.eventTime).strftime(
                        '%Y-%m-%d %H:%M')
                    write_history.write(resource_history.resourceId + "\t" + resource_history.fromEvent + "\t"
                                        + resource_history.event + "\t" + event_time + "\t" + str(
                        resource_history.duration) + "\t"
                                        + resource_history.fromStatus + "\t" + resource_history.toStatus + "\t"
                                        + resource_history.operationId + "\t" + resource_history.lotPriorOperationId + "\t"
                                        + resource_history.productIdProcessed + "\t" + resource_history.lotIdProcessed + "\n")

    def conflict_status_init(self):
        conflict_dict = defaultdict(lambda: defaultdict(int))
        for product_id, _ in self.info.productionRequirement.items():
            currentProduct = self.info.productMap[product_id]
            assert isinstance(currentProduct, Product)
            temp_oper_list = currentProduct.operationSequence.operationSequence[0:-1]
            for temp_oper in temp_oper_list:
                for model_id, model in self.info.resourceModelMap.items():
                    if product_id in model.resourceArrangementMap:
                        if temp_oper in model.resourceArrangementMap[product_id]:
                            self.conflict_dict[product_id][temp_oper].add(model_id)

        for product_id, oper_model_dict in self.conflict_dict.items():
            for operation_id, resource_model_set in oper_model_dict.items():
                for resource_model_id in resource_model_set:
                    self.feasible_resource_list_per_product_oper[product_id][operation_id].extend(
                        self.existResourceIdMap[resource_model_id])

        for lot_id, lot in self.info.lotMap.items():
            assert isinstance(lot, Lot)
            temp_product_id = lot.productId
            temp_operation_id = lot.currentOperationId
            latest_history = lot.historyList[-1]
            assert isinstance(latest_history, LotHistory)
            lat_from_event = latest_history.fromEvent
            lat_current_event = latest_history.event
            lat_to_location = latest_history.toLocationId[0:5]
            self.conflict_lot_location[temp_product_id + '/' + temp_operation_id][
                lat_from_event + '/' + lat_current_event + '/' + lat_to_location] += 1

            self.lot_count_per_loc[lat_from_event + '/' + lat_current_event + '/' + lat_to_location] += 1

            # model_set = self.conflict_dict[temp_product_id][temp_operation_id]
            # for model in model_set:
            #     self.lot_set_of_loc_per_model[model][
            #         lat_from_event + '/' + lat_current_event + '/' + lat_to_location].add(lot_id)

    def update_confliting_lots(self, lot):
        assert isinstance(lot, Lot)
        temp_product_id = lot.productId
        temp_operation_id = lot.currentOperationId
        latest_history = lot.historyList[-1]
        before_latest_history = lot.historyList[-2]
        assert isinstance(latest_history, LotHistory)
        assert isinstance(before_latest_history, LotHistory)
        lat_from_event = latest_history.fromEvent
        lat_current_event = latest_history.event
        lat_to_location = latest_history.toLocationId[0:5]
        lat_operation_id = latest_history.operationId

        bef_from_event = before_latest_history.fromEvent
        bef_current_event = before_latest_history.event
        bef_to_location = before_latest_history.toLocationId[0:5]
        bef_operation_id = before_latest_history.operationId

        self.conflict_lot_location[temp_product_id + '/' + lat_operation_id][lat_from_event + '/' + lat_current_event + '/' + lat_to_location] += 1
        self.conflict_lot_location[temp_product_id + '/' + bef_operation_id][
            bef_from_event + '/' + bef_current_event + '/' + bef_to_location] -= 1

        self.lot_count_per_loc[lat_from_event + '/' + lat_current_event + '/' + lat_to_location] += 1
        self.lot_count_per_loc[bef_from_event + '/' + bef_current_event + '/' + bef_to_location] -= 1

    def get_paper_state_for_bottleneck(self, currentLot, resource, currentOperation, targetOperation):
        assert isinstance(currentLot, Lot)
        assert isinstance(resource, Resource)
        current_product_id = currentLot.productId
        current_operation_id = currentLot.currentOperationId
        current_flow_number = currentLot.flowNumber
        current_product = self.info.productMap[current_product_id]
        assert isinstance(current_product, Product)
        next_operation_id = current_product.operationSequence.operationSequence[current_flow_number + 1]
        waiting_lot = True
        # 작업 중인 Lot이 Candidate lot에 있을 경우
        if targetOperation not in next_operation_id:
            next_operation_id = current_product.operationSequence.operationSequence[current_flow_number + 2]
            waiting_lot = False

        pos_resource_models = self.conflict_dict[current_product_id][next_operation_id]
        assignment_vector = [0] * (12 + len(self.loc_names_for_state_making))
        # assignment_vector = [0] * 7

        if len(self.temporary_conflict_state[current_product_id][next_operation_id]) == 0:
            for lot_in, lot in self.info.lotMap.items():
                temp_product_id = lot.productId
                temp_product = self.info.productMap[temp_product_id]
                temp_index = -1
                temp_flow_num = -1
                if 'DA_BUF' in lot.lotLocation and lot.lotStatus == 'MOVE':
                    temp_index = 0
                    temp_flow_num = lot.flowNumber + 1
                elif 'DA_BUF' in lot.lotLocation and lot.lotStatus == 'WAIT':
                    temp_index = 1
                    temp_flow_num = lot.flowNumber + 1
                elif 'DA_RES' in lot.lotLocation:
                    temp_flow_num = lot.flowNumber + 1
                    temp_index = 2
                elif 'WAY TO WB_STOCK' == lot.lotLocation:
                    temp_flow_num = lot.flowNumber
                    temp_index = 3
                elif lot.lotLocation == 'WB_STOCK':
                    temp_flow_num = lot.flowNumber
                    temp_index = 4
                if temp_index > -1:
                    temp_operation_id = temp_product.operationSequence.operationSequence[temp_flow_num]
                    if 'WB' not in temp_operation_id:
                        print(temp_operation_id, '!!!!!!!!!!!! ERROR: WB NOT IN CONFLICTING SITUATION')
                    temp_pos_res_models = self.conflict_dict[lot.productId][temp_operation_id]
                    if pos_resource_models & temp_pos_res_models:
                        assignment_vector[temp_index] += 1
            self.temporary_conflict_state[current_product_id][next_operation_id] = assignment_vector
        else:
            assignment_vector = self.temporary_conflict_state[current_product_id][next_operation_id]

        # The number of WB resources that able to process currentLot
        assignment_vector[5] = len(self.feasible_resource_list_per_product_oper[current_product_id][next_operation_id])
        # Delay Time
        """Until track in time"""
        remainingTime = max(0, resource.lastWorkFinishTime + resource.processingTimeInBuffer - self.T)
        currentResourceRemainingTime = 0
        if currentLot.currentResourceId != "":  # currentLot under processing
            currentResourceRemainingTime = self.info.resourceMap[
                                               currentLot.currentResourceId].lastWorkFinishTime - self.T
        else:
            recentHistory = currentLot.historyList[-1]
            if recentHistory.event == 'MOVE END' or recentHistory.event == 'FACTORY IN':
                currentResourceRemainingTime = -self.parameters.moveTime
            elif recentHistory.event == 'MOVE START':
                currentResourceRemainingTime = recentHistory.eventTime - self.T
            else:
                print("ERROR!! Unexpected DASelectionCandidateLot Exists : ", lot.lotId, recentHistory.event, "\t",
                      recentHistory.eventTime)
        expectedTrackInTime = currentResourceRemainingTime + self.parameters.moveTime * 2
        untilTrackInTime = max(expectedTrackInTime, remainingTime)
        assignment_vector[6] = untilTrackInTime

        """ 
        Lot - related State
        * 7 : Lot Size
        * 8 : Progress Rate of same product
        * 9 : current flow number
        """
        assignment_vector[7] = currentLot.lotQuantity
        assignment_vector[8] = self.counters.current_finished_lot_per_product[currentLot.productId] / self.counters.total_lot_per_product[currentLot.productId]
        assignment_vector[9] = currentLot.flowNumber

        """
        Resource-related State (For given resource)
        * 10 : remaining Time
        * 11 : Processing Time
        """
        assignment_vector[10] = max(resource.lastWorkFinishTime - self.T, 0)
        if waiting_lot is False:
            temp_operation_id = current_product.operationSequence.operationSequence[current_flow_number + 1]
            currentLot.currentOperationId = temp_operation_id
            assignment_vector[11] = self.get_processing_time(resource, currentLot)
            currentLot.currentOperationId = current_operation_id
        else:
            assignment_vector[11] = self.get_processing_time(resource, currentLot)

        # LOT DUE DATE
        # assignment_vector[8] = currentLot.lotDueDate
        """
        Snap Shot State (For given resource)
        """
        for index in range(len(self.loc_names_for_state_making)):
            loc_name = self.loc_names_for_state_making[index]
            assignment_vector[index+12] = self.lot_count_per_loc[loc_name]

        return assignment_vector

    def get_snapshot_state(self, resource, candidate_lots):
        assert isinstance(resource, Resource)
        num_of_features_except_locs = 13
        assignment_vector = [0] * (num_of_features_except_locs + len(self.loc_names_for_state_making))
        """
        Resource-related State (For given resource)
        * 0 : remaining Time
        """
        assignment_vector[0] = max(resource.lastWorkFinishTime - self.T, 0)

        """
        Snap Shot State: Statistics of candidate lots 
        
        """
        min_factory_in_time = sys.maxsize
        max_factory_in_time = 0.0
        avg_factory_in_time = 0.0
        min_quantity = sys.maxsize
        max_quantity = 0.0
        avg_quantity = 0.0
        min_remaining = sys.maxsize
        max_remaining = 0.0
        avg_remaining = 0.0
        min_processing_time = sys.maxsize
        max_processing_time = 0.0
        avg_processing_time = 0.0

        not_available_this_resource = 0
        for temp_lot in candidate_lots:
            assert isinstance(temp_lot, Lot)
            # Factory in time related
            if temp_lot.factoryInTime < min_factory_in_time:
                min_factory_in_time = temp_lot.factoryInTime
            elif temp_lot.factoryInTime > max_factory_in_time:
                max_factory_in_time = temp_lot.factoryInTime
            avg_factory_in_time += temp_lot.factoryInTime
            # Quantity related
            if temp_lot.lotQuantity < min_quantity:
                min_quantity = temp_lot.lotQuantity
            elif temp_lot.lotQuantity > max_quantity:
                max_quantity = temp_lot.lotQuantity
            avg_quantity += temp_lot.lotQuantity
            # remaining operation related
            remaining_oper = self.info.flowMap[temp_lot.flowId].getTotalFlowDegree() - temp_lot.flowNumber
            if remaining_oper < min_remaining:
                min_remaining = remaining_oper
            elif self.info.flowMap[temp_lot.flowId].getTotalFlowDegree() - temp_lot.flowNumber > max_remaining:
                max_remaining = remaining_oper
            avg_remaining += remaining_oper
            # processing time related
            resourceModel = self.info.resourceModelMap[resource.resourceModelId]
            assert isinstance(resourceModel, ResourceModel)
            if 'WB' in temp_lot.lotLocation or temp_lot.lotStatus == 'PROCESS':
                temp_operation_id = temp_lot.currentOperationId
                temp_lot.currentOperationId = self.info.flowMap[temp_lot.flowId].getNowOperation(temp_lot.flowNumber + 1)
                if temp_lot.currentOperationId not in resourceModel.resourceArrangementMap[temp_lot.productId]:
                    not_available_this_resource += 1
                    continue
                temp_lot.processingTime = self.get_processing_time(resource, temp_lot)
                temp_lot.currentOperationId = temp_operation_id
            else:
                if temp_lot.currentOperationId not in resourceModel.resourceArrangementMap[temp_lot.productId]:
                    not_available_this_resource += 1
                    continue
                temp_lot.processingTime = self.get_processing_time(resource, temp_lot)
            temp_processing_time = temp_lot.processingTime
            if temp_processing_time < min_processing_time:
                min_processing_time = temp_processing_time
            elif temp_processing_time > max_processing_time:
                max_processing_time = temp_processing_time
            avg_processing_time += temp_processing_time

        avg_factory_in_time /= len(candidate_lots)
        avg_quantity /= len(candidate_lots)
        avg_remaining /= len(candidate_lots)
        avg_processing_time /= len(candidate_lots)

        assignment_vector[1] = max(min_factory_in_time, 0)
        assignment_vector[2] = max_factory_in_time
        assignment_vector[3] = max(avg_factory_in_time, 0)
        assignment_vector[4] = min_quantity
        assignment_vector[5] = max_quantity
        assignment_vector[6] = avg_quantity
        assignment_vector[7] = min_remaining
        assignment_vector[8] = max_remaining
        assignment_vector[9] = avg_remaining
        assignment_vector[10] = min_processing_time
        assignment_vector[11] = max_processing_time
        assignment_vector[12] = avg_processing_time

        """
        Snap Shot State: # of lots across the location 
        """
        for index in range(len(self.loc_names_for_state_making)):
            loc_name = self.loc_names_for_state_making[index]
            assignment_vector[index + num_of_features_except_locs] = self.lot_count_per_loc[loc_name]

        return assignment_vector

    def rtd_score(self, score_nor=None):
        production_info = self.info
        waitingtime = dict()
        for lotId in production_info.lotMap:
            if 'WIP' in lotId:
                continue
            currentLot = production_info.lotMap[lotId]
            if currentLot.historyList[-1].event != 'FACTORY OUT':
                continue
            fromoperationid = ''
            for lotHistory in currentLot.historyList:
                if 'DA' in lotHistory.fromOperationId and 'WB' in lotHistory.toOperationId:
                    fromoperationid = lotHistory.fromOperationId
                # 170927) Split 없앤 후 rtd_score 계산 수정
                if 'WB' in lotHistory.operationId and lotHistory.fromEvent == 'MOVE END' and lotHistory.event == 'MOVE START':
                    if not lotHistory.lotId + "_" + fromoperationid in waitingtime:
                        waitingtime[lotHistory.lotId + "_" + fromoperationid] = lotHistory.duration
                    else:
                        print('is possible?')
                    continue
                if 'DA' in lotHistory.fromOperationId and 'DA' in lotHistory.toOperationId and (int(lotHistory.fromOperationId[2]) + 1) == int(lotHistory.toOperationId[2]):
                    waitingtime[lotHistory.lotId + "_" + lotHistory.fromOperationId] = -1
                    continue

        for key in waitingtime:
            if waitingtime[key] == -1:
                operationId = key.split('_')[1]
                operation = operationId[:2]
                operationNo = int(operationId[2])
                nextOperation = operation + str(operationNo + 1)
                waitingtime[key] = waitingtime[key.split('_')[0] + '_' + nextOperation]

        idletime = dict()
        for resourceId in production_info.resourceMap:
            currentResource = production_info.resourceMap[resourceId]
            for resourceHistory in currentResource.historyList:
                if 'WIP' in resourceHistory.lotIdProcessed:
                    continue
                if 'DA' in resourceHistory.lotPriorOperationId and resourceHistory.fromStatus == 'IDLE':
                    lotIdForScoring = resourceHistory.lotIdProcessed
                    temp_lot = production_info.lotMap[resourceHistory.lotIdProcessed]
                    if temp_lot.historyList[-1].event != 'FACTORY OUT':
                        continue
                    if '_' in resourceHistory.lotIdProcessed:
                        lotIdForScoring = lotIdForScoring.split("_")[0]
                    if 'DA' in resourceHistory.operationId:
                        idletime[lotIdForScoring + "_" + resourceHistory.lotPriorOperationId] = -1
                    else:
                        if not lotIdForScoring + "_" + resourceHistory.lotPriorOperationId in idletime:
                            idletime[lotIdForScoring + "_" + resourceHistory.lotPriorOperationId] = resourceHistory.duration
                        else:
                            idletime[lotIdForScoring + "_" + resourceHistory.lotPriorOperationId] = resourceHistory.duration + idletime[lotIdForScoring + "_" + resourceHistory.lotPriorOperationId]

        for key in idletime:
            if idletime[key] == -1:
                operationId = key.split('_')[1]
                operation = operationId[:2]
                operationNo = int(operationId[2])
                nextOperation = operation + str(operationNo + 1)
                idletime[key] = idletime[key.split('_')[0] + '_' + nextOperation]

        for key in waitingtime.keys():
            reward = list()
            reward.append(waitingtime[key])
            reward.append(idletime[key])
            reward.append(waitingtime[key] + idletime[key])
            if score_nor is not None:
                if self.info.needScoreNormalization:
                    score_nor.append_score(reward)
                else:
                    if self.parameters.normalization:
                        normalized_score = score_nor.normalize(reward, method='MeanMax', score_range=[0, 1])
                        self.rtd_rec.addReward(key.split('_')[0], key.split('_')[1], normalized_score)
                    else:
                        self.rtd_rec.addReward(key.split('_')[0], key.split('_')[1], reward)
            else:
                self.rtd_rec.addReward(key.split('_')[0], key.split('_')[1], waitingtime[key] + idletime[key])

    def DA_waiting_score(self, DA_score_nor=None):
        production_info = self.info
        for lotId in production_info.lotMap:
            if 'WIP' in lotId:
                continue
            currentLot = production_info.lotMap[lotId]
            if currentLot.historyList[-1].event != 'FACTORY OUT':
                continue
            for lotHistory in currentLot.historyList:
                if 'DA' in lotHistory.operationId and lotHistory.fromEvent == 'MOVE END' and lotHistory.event == 'MOVE START':
                    DA_score_nor.append_score(lotHistory.duration)

    def get_operationId_forReserve(self, lot, o_type):
        assert isinstance(lot, Lot)
        o = lot.currentOperationId
        if o_type == 'DA':
            if 'WB' in lot.lotLocation or lot.lotStatus == 'PROCESS':
                o = self.info.flowMap[lot.flowId].getNowOperation(lot.flowNumber + 1)
        elif o_type == 'WB':
            if lot.lotStatus == 'PROCESS':
                o = self.info.flowMap[lot.flowId].getNowOperation(lot.flowNumber + 1)
        return o

    def viewerWriter(self, problem_idx, avg_TAT):
        f = open(
            "%d_" % problem_idx + "_" + self.parameters.DARTDPolicy + "_" + self.parameters.WBRTDPolicy + "_%f.txt" % avg_TAT, 'w')
        jo = dict()

        a = 0
        for lotId in self.info.lotMap:
            currentLot = self.info.lotMap[lotId]
            for lotHistory in currentLot.historyList:
                if lotHistory.reservationTime != -1:
                    resourceId = lotHistory.toResourceId
                    currentResource = self.info.resourceMap[resourceId]
                    resourceHistoryList = currentResource.historyList
                    starttime = lotHistory.reservationTime
                    endtime = lotHistory.eventTime
                    for resourceHistory in resourceHistoryList:
                        if resourceHistory.event == "END PROD":
                            if lotHistory.reservationTime < resourceHistory.eventTime and lotHistory.eventTime >= resourceHistory.eventTime:
                                starttime = resourceHistory.eventTime
                                break
                    for resourceHistory in resourceHistoryList:
                        if resourceHistory.event == "START SETUP":
                            # if lotHistory.reservationTime <= resourceHistory.eventTime and lotHistory.eventTime > resourceHistory.eventTime:
                            if starttime <= resourceHistory.eventTime and endtime > resourceHistory.eventTime:
                                endtime = resourceHistory.eventTime
                                break
                    if self.ganttChart.scheduleForResource[resourceId]:
                        self.ganttChart.scheduleForResource[resourceId].append(
                            Gantt(a, starttime, endtime, lotHistory.productId, "RESERVED", 0, "", 0))
                    else:
                        ganttChart = list(Gantt)
                        ganttChart.add(Gantt(a, starttime, endtime, lotHistory.productId, "RESERVED", 0, "", 0))
                        self.ganttChart.scheduleForResource[resourceId] = ganttChart
                    a -= 1  # reserved는 계속 - 방향으로 값을 증가시키면서 아이디를 주는 방식?

        Gant = list()
        od = OrderedDict(sorted(self.ganttChart.scheduleForResource.items()))  # 이 부분은 어떤 목적??
        for resourceId in od:
            resource = dict()
            lots = list()
            for gantt in od[resourceId]:
                new_start_time = datetime.fromtimestamp(self.start_time + gantt.starting_time).strftime(
                    '%Y-%m-%d %H:%M:%S')
                new_end_time = datetime.fromtimestamp(
                    self.start_time + gantt.starting_time + gantt.ending_time).strftime('%Y-%m-%d %H:%M:%S')
                lot = {"eventId": gantt.eventId, "starting_time": self.milToSec(gantt.starting_time),
                       "ending_time": self.milToSec(gantt.ending_time),
                       "productId": gantt.productId, "productGroup": self.info.productMap[gantt.productId].productGroup,
                       "lotId": gantt.lotId, "quantity": gantt.quantity, "degree": gantt.degree,
                       "flow": gantt.flow, 'new_start_time': new_start_time, 'new_end_time': new_end_time}
                lots.append(lot)
            resource["label"] = resourceId
            resource["resourceModel"] = self.info.resourceMap[resourceId].resourceModelId
            resource["times"] = lots
            Gant.append(resource)

        jo["Gantt"] = Gant

        Product = dict()
        for productId in self.info.productMap:
            product = {"productName": self.info.productMap[productId].productName,
                       "productGroup": self.info.productMap[productId].productGroup,
                       "flowId": self.info.productMap[productId].flowId,
                       "operationSequence": str(self.info.productMap[productId].operationSequence.operationSequence)}
            Product[productId] = product
        jo["Product"] = Product

        DAResourceNum = 0
        WBResourceNum = 0
        for resourceId in self.info.resourceMap:
            if "DA" in resourceId:
                DAResourceNum += 1
            if "WB" in resourceId:
                WBResourceNum += 1

        Decision = dict()
        # if DARTDPolicy == "learner":
        if self.decisionList:
            prevDecision = self.decisionList[0]
            decisionMap = dict()
            decisionViewList = list()
            for decision in self.decisionList:
                if decision.decisionId == prevDecision.decisionId:
                    decisionViewList.append(decision)
                else:
                    decisionMap[prevDecision.decisionId] = decisionViewList
                    decisionViewList = list()
                    decisionViewList.append(decision)
                prevDecision = decision
            decisionMap[decision.decisionId] = decisionViewList

            for decisionId in decisionMap:
                candidates = list()
                values = sorted(decisionMap[decisionId], key=lambda x: x.loss, reverse=True)
                cnt = 0
                for dv in values:
                    cnt += 1
                    if cnt == 1:
                        decisionKey = dv.operationId + "_" + dv.lotId
                    candidate = {"decisionType": dv.decisionType, "decisionTime": 1000 * dv.decisionTime - 32400000,
                                 "lotId": dv.lotId,
                                 "decision": dv.decision, "operationId": dv.operationId, "productType": dv.productType,
                                 "lotSize": dv.lotSize, "dawipLevel": dv.dawipLevel, "wbwipLevel": dv.wbwipLevel,
                                 "workingDA": dv.workingDA, "workingWB": dv.workingWB, "inputCount": dv.inputCount,
                                 "outputCount": dv.outputCount, "currentCSTQuantity": dv.currentCSTQuantity,
                                 "flowId": dv.flowId, "currentLocation": dv.currentLocation,
                                 "sc_w": float(dv.waiting), 'sc_l': float(dv.idle), 'sc_d': float(dv.d_waiting), 'loss': float(dv.loss)}
                    self.counters.DAUtilizationPerTimestamp[dv.decisionTime] = dv.workingDA / DAResourceNum
                    self.counters.WBUtilizationPerTimestamp[dv.decisionTime] = dv.workingWB / WBResourceNum
                    candidates.append(candidate)
                Decision[decisionKey] = candidates

        jo["Decision"] = Decision
        jo['actionAttribute'] = []
        ProductionStatus = list()
        maxtime = 0

        shipcount = dict()
        shipcount["id"] = "ShipCount"
        lots = list()
        for i in sorted(self.counters.ShipCount):
            lot = {"time": self.milToSec(i), "number": self.counters.ShipCount[i]}
            lots.append(lot)
            if maxtime < i:
                maxtime = i
        shipcount["values"] = lots
        ProductionStatus.append(shipcount)

        util = dict()
        util['id'] = 'util'
        temp_util = {}
        lots = list()
        for i in sorted(self.counters.DAUtilizationPerTimestamp):
            lot = {"time": self.milToSec(i), "number": self.counters.DAUtilizationPerTimestamp[i]}
            lots.append(lot)
            if maxtime < i:
                maxtime = i
        temp_util["DA"] = lots
        lots = list()
        for i in sorted(self.counters.WBUtilizationPerTimestamp):
            lot = {"time": self.milToSec(i), "number": self.counters.WBUtilizationPerTimestamp[i]}
            lots.append(lot)
            if maxtime < i:
                maxtime = i
        temp_util["WB"] = lots
        util['values'] = temp_util
        ProductionStatus.append(util)

        inputcount = dict()
        inputcount["id"] = "InputCount"
        lots = list()
        max_inputcount = 0
        for i in sorted(self.counters.InputCount):
            lot = {"time": self.milToSec(i), "number": self.counters.InputCount[i]}
            lots.append(lot)
            if maxtime < i:
                maxtime = i
            max_inputcount += 1
        inputcount["values"] = lots
        ProductionStatus.append(inputcount)

        intargetcount = dict()
        intargetcount["id"] = "InTargetCount"
        lots = list()
        intarget_dict = {}
        for product_id, quantity_per_time in self.counters.inTargetCountByProduct.items():
            values = []
            for time in sorted(quantity_per_time):
                temp_object = {'time': self.milToSec(time), 'number': quantity_per_time[time] }
                values.append(temp_object)
            intarget_dict[product_id] = values
        intargetcount["values"] = intarget_dict
        ProductionStatus.append(intargetcount)

        wiplevel = dict()
        wiplevel["id"] = "WIPLevel"
        lots = list()
        cnt = 0
        wipcnt = 0
        for i in sorted(self.counters.WIPLevel):
            lot = {"time": self.milToSec(i), "number": self.counters.WIPLevel[i]}
            lots.append(lot)
            if maxtime < i:
                maxtime = i
            cnt += 1
            wipcnt += self.counters.WIPLevel[i]
        AVG_Wiplevel = 0
        if cnt != 0:
            AVG_Wiplevel = wipcnt / cnt

        da_values = list()
        wb_values = list()
        wip_dict = {}
        for time in sorted(self.counters.daWIPLevel):
            da_object = {'time': self.milToSec(time), 'number': self.counters.daWIPLevel[time]}
            wb_object = {'time': self.milToSec(time), 'number': self.counters.wbWIPLevel[time]}
            da_values.append(da_object)
            wb_values.append(wb_object)
        wip_dict['DA'] = da_values
        wip_dict['WB'] = wb_values
        wiplevel["values"] = wip_dict
        ProductionStatus.append(wiplevel)

        WIP_level_per_product = dict()
        WIP_level_per_product['id'] = 'WIP_level_per_product'
        WIP_levels = list()

        for productId, operation_dict in self.WIP_level_per_T_product.items():
            temp_product = {}
            temp_operation = {}
            for operation, flow_dict in operation_dict.items():
                temp_flow = []
                for operation_id, time_dict in flow_dict.items():
                    if operation_id == 'DA1':
                        continue
                    values = list()
                    for time in sorted(time_dict):
                        temp_object = {'time': self.milToSec(time), 'number': time_dict[time]}
                        values.append(temp_object)
                    temp_id_object = {'id': operation_id, 'plots': values}
                    temp_flow.append(temp_id_object)
                values = list()
                for time in sorted(self.WIP_level_per_T_product_agg[productId][operation]):
                    temp_object = {'time': self.milToSec(time),
                                   'number': self.WIP_level_per_T_product_agg[productId][operation][time]}
                    values.append(temp_object)
                temp_id_object = {'id': 'all', 'plots': values}
                temp_flow.append(temp_id_object)
                temp_operation[operation] = temp_flow
            temp_product[productId] = temp_operation
            WIP_levels.append(temp_product)
        WIP_level_per_product['values'] = WIP_levels
        ProductionStatus.append(WIP_level_per_product)

        best_EQP_per_product = dict()
        best_EQP_per_product['id'] = 'best_EQP'
        EQPs = list()

        for operation, product_dict in self.best_EQP_per_T_product.items():
            temp_operation = {}
            temp_product = {}
            for product_id, time_dict in product_dict.items():
                values = list()
                for time in sorted(time_dict):
                    temp_object = {'time': self.milToSec(time), 'number': time_dict[time]}
                    values.append(temp_object)
                temp_product[product_id] = values
            setuped_list = self.conducted_setup_record[operation]
            setup_list = list()
            for setup_info in setuped_list:
                temp_object = {'time': self.milToSec(setup_info['time']), 'from': setup_info['from'],
                               'to': setup_info['to']}
                setup_list.append(temp_object)
            temp_product['setup'] = setup_list
            temp_operation[operation] = temp_product
            EQPs.append(temp_operation)
        best_EQP_per_product['values'] = EQPs
        ProductionStatus.append(best_EQP_per_product)

        jo["ProductionStatus"] = ProductionStatus

        KPIMaxTime = [maxtime * 1000]
        jo["KPIMaxTime"] = KPIMaxTime

        waitingTime = 0
        for i in sorted(self.KPIs.waitingMap):
            waitingTime += self.KPIs.waitingMap[i]

        DENOMINATOR = {"Stocker_size": 0, "DA_resource": DAResourceNum, "WB_resource": WBResourceNum,
                       "MAX_inputcount": max_inputcount, "MAX_outputcount": len(self.KPIs.TATMap)}
        jo["DENOMINATOR"] = DENOMINATOR

        load_analysis = {}
        product_info = list()
        target_info = dict()
        load_info = defaultdict(lambda: defaultdict(list))

        processing_time_per_operation = self.get_processing_time_per_operation()
        exp_production_load = defaultdict(lambda: defaultdict(list))

        for product_id, dict_per_operation in self.production_load.items():
            for operation_id, capa_list in dict_per_operation.items():
                load_info_list = list()
                for day, capa in enumerate(capa_list):
                    if day > 2:
                        expected_capa = 0
                        actual_capa = capa / 24 / 3600
                    else:
                        # expected_capa = processing_time_per_operation[product_id][operation_id] * 0
                        expected_capa = processing_time_per_operation[product_id][operation_id] * \
                                        self.info.intarget[product_id][day] / 24 / 3600
                        actual_capa = capa / 24 / 3600
                    load_info_daily = {'expected': expected_capa, 'actual': actual_capa}
                    load_info_list.append(load_info_daily)
                load_info[product_id][operation_id] = load_info_list

        load_analysis['LoadInfo'] = load_info
        jo["LoadAnalysis"] = load_analysis

        total_intarget = 0
        actual_intarget = 0
        for product_id, target_list in self.info.intarget.items():
            target_info_list = list()
            for day, target in enumerate(target_list):
                total_intarget += target
                actual_intarget += self.counters.inTargetCompletion[day][product_id]
                target_info_daily = {'target': target, 'actual': self.counters.inTargetCompletion[day][product_id]}
                target_info_list.append(target_info_daily)
            target_info[product_id] = target_info_list
            product_json = {}
            product_instance = self.info.productMap[product_id]
            product_json['productId'] = product_instance.productId
            product_json['productName'] = product_instance.productName
            product_json['productGroup'] = product_instance.productGroup
            product_json['flowId'] = product_instance.flowId
            processingTimeJson = {'DA': processing_time_per_operation[product_id]['DA'],
                                  'WB': processing_time_per_operation[product_id]['WB']}
            product_json['processingTime'] = processingTimeJson
            product_info.append(product_json)

        load_analysis['ProductInfo'] = product_info
        load_analysis['TargetInfo'] = target_info

        KPI = {"Util_DA": self.sr.utilizationPerOperation["DA"],
               "Util_WB": self.sr.utilizationPerOperation["WB"],
               # "InTarget": actual_intarget / total_intarget,
               "InTarget": actual_intarget / 1,
               "Stocker_size": 0, "Makespan": self.sr.makespan,
               "AVGWiplevel": AVG_Wiplevel,
               "WaitingTimeRatio": self.sr.total_WaitingTime / self.sr.total_TAT,
               "TotalWaitingTime": self.sr.total_WaitingTime,
               "TotalTAT": self.sr.total_TAT}
        jo["KPI"] = KPI

        jsonString = json.dumps(jo)
        f.write(jsonString)
        f.close()

    def milToSec(self, mil):
        result = mil * 1000 - 32400000
        return result

    # Viewer의 Load Analysis에만 사용됨
    def get_processing_time_per_operation(self):
        processing_time_per_operation_id = defaultdict(lambda: defaultdict(float))
        processing_time_per_operation = defaultdict(lambda: defaultdict(float))

        num_DA_model = 0
        num_WB_model = 0
        for resource_model_id, resource_model in self.info.resourceModelMap.items():
            assert isinstance(resource_model, ResourceModel)
            resource_arrangement_map = resource_model.resourceArrangementMap
            final_operation_id = resource_model.operationId
            if final_operation_id == 'DA':
                num_DA_model += 1
            elif final_operation_id == "WB":
                num_WB_model += 1
            for product_id, resource_arrangement_dict in resource_arrangement_map.items():
                for operation_id, resource_arrangement in resource_arrangement_dict.items():
                    processing_time_per_operation_id[product_id][operation_id] += resource_arrangement.processingTime

        for product_id, dict_per_operation_id in processing_time_per_operation_id.items():
            for operation_id, processing_time_sum in dict_per_operation_id.items():
                denominator = 1
                ratio = 1
                if 'DA' in operation_id:
                    denominator = num_DA_model
                    ratio = self.info.DASTRatio
                elif 'WB' in operation_id:
                    denominator = num_WB_model
                    ratio = self.info.WBSTRatio
                processing_time_per_operation[product_id][
                    operation_id[0:2]] += processing_time_sum * ratio / denominator

        return processing_time_per_operation

    def lot_choice(self, Lotlist, ruleType, selectedRes=None):
        selectedLot = None
        if 'random' in ruleType:
            selectedLot = random.choice(Lotlist)
        elif ruleType == 'FIFO':
            temp_lot_list = []
            for temp_lot in Lotlist:
                if temp_lot.factoryInTime > 0:
                    temp_lot_list.append(temp_lot)
            if len(temp_lot_list) > 0:
                temp_lot_list.sort(key=lambda l: l.factoryInTime)
                # temp_lot_list.sort(key=lambda l: (l.factoryInTime, l.lotId))
                selectedLot = temp_lot_list[0]
            else:
                Lotlist.sort(key=lambda l: l.factoryInTime)
                # Lotlist.sort(key=lambda l: (l.factoryInTime, l.lotId))
                selectedLot = Lotlist[0]
        elif ruleType == 'LIFO':
            temp_lot_list = []
            for temp_lot in Lotlist:
                if temp_lot.factoryInTime > 0:
                    temp_lot_list.append(temp_lot)
            if len(temp_lot_list) > 0:
                temp_lot_list.sort(key=lambda l: l.factoryInTime)
                # temp_lot_list.sort(key=lambda l: (l.factoryInTime, l.lotId))
                selectedLot = temp_lot_list[-1]
            else:
                Lotlist.sort(key=lambda l: l.factoryInTime)
                # Lotlist.sort(key=lambda l: (l.factoryInTime, l.lotId))
                selectedLot = Lotlist[-1]
        elif ruleType == 'LOR':
            Lotlist.sort(key=lambda l: self.info.flowMap[l.flowId].getTotalFlowDegree() - l.flowNumber)
            # Lotlist.sort(key=lambda l: (self.info.flowMap[l.flowId].getTotalFlowDegree() - l.flowNumber, l.lotId))
            selectedLot = Lotlist[0]
        elif ruleType == 'MOR':
            Lotlist.sort(key=lambda l: self.info.flowMap[l.flowId].getTotalFlowDegree() - l.flowNumber)
            # Lotlist.sort(key=lambda l: (self.info.flowMap[l.flowId].getTotalFlowDegree() - l.flowNumber, l.lotId))
            selectedLot = Lotlist[-1]
        elif ruleType == 'small':
            Lotlist.sort(key=lambda l: l.lotQuantity)
            # Lotlist.sort(key=lambda l: (l.lotQuantity, l.lotId))
            selectedLot = Lotlist[0]
        elif ruleType == 'large':
            Lotlist.sort(key=lambda l: l.lotQuantity)
            # Lotlist.sort(key=lambda l: (l.lotQuantity, l.lotId))
            selectedLot = Lotlist[-1]
        elif ruleType == 'SPT' or ruleType == 'LPT':
            for temp_lot in Lotlist:
                assert isinstance(temp_lot, Lot)
                if temp_lot.lotStatus == 'PROCESS':
                    temp_operation_id = temp_lot.currentOperationId
                    temp_lot.currentOperationId = self.info.flowMap[temp_lot.flowId].getNowOperation(temp_lot.flowNumber+1)
                    temp_lot.processingTime = self.get_processing_time(selectedRes, temp_lot)
                    temp_lot.currentOperationId = temp_operation_id
                else:
                    temp_lot.processingTime = self.get_processing_time(selectedRes, temp_lot)
            Lotlist.sort(key=lambda l: l.processingTime)
            if ruleType == 'SPT':
                selectedLot = Lotlist[0]
            else:
                selectedLot = Lotlist[-1]
        elif ruleType == 'FLNQ':
            temp_candi_dict = defaultdict(list)
            for cand_lot in Lotlist:
                next_operation_id = self.info.flowMap[cand_lot.flowId].getNowOperation(cand_lot.flowNumber + 1)
                if cand_lot.lotStatus == 'PROCESS':
                    next_operation_id = self.info.flowMap[cand_lot.flowId].getNowOperation(cand_lot.flowNumber + 2)
                lot_num_in_wb_stock = self.check_lot_in_WB_stock[cand_lot.productId][next_operation_id]
                temp_candi_dict[lot_num_in_wb_stock].append(cand_lot)
            sorted_keys = sorted(temp_candi_dict)
            lot_list = temp_candi_dict[sorted_keys[0]]
            selectedLot = random.choice(lot_list)
        elif ruleType == 'LNQ' or ruleType == 'SNQ':
            temp_count_dict = defaultdict(lambda: defaultdict(int))
            temp_lot_dict = defaultdict(lambda: defaultdict(list))
            for temp_lot in Lotlist:
                assert isinstance(temp_lot, Lot)
                if temp_lot.lotStatus == 'PROCESS':
                    temp_operation_id = self.info.flowMap[temp_lot.flowId].getNowOperation(temp_lot.flowNumber + 1)
                    temp_count_dict[temp_lot.productId][temp_operation_id] += 1
                    temp_lot_dict[temp_lot.productId][temp_operation_id].append(temp_lot)
                else:
                    temp_count_dict[temp_lot.productId][temp_lot.currentOperationId] += 1
                    temp_lot_dict[temp_lot.productId][temp_lot.currentOperationId].append(temp_lot)
            temp_list = []
            for main_key, sub_dict in temp_count_dict.items():
                for sub_key, value in sorted(sub_dict.items(), key=lambda x: x[1]):
                    temp_list.append((main_key, sub_key, value))
            if ruleType == 'LNQ':
                temp_list.sort(key=lambda x: x[2], reverse=True)
            else:
                temp_list.sort(key=lambda x: x[2])
            temp_value = temp_list[0]
            selectedLot = random.choice(temp_lot_dict[temp_value[0]][temp_value[1]])
        elif ruleType == 'STOCK':
            temp_list = []
            for temp_lot in Lotlist:
                if 'STOCK' in temp_lot.lotLocation:
                    temp_list.append(temp_lot)
            if len(temp_list) > 0:
                selectedLot = random.choice(temp_list)
            else:
                selectedLot = random.choice(Lotlist)
        return selectedLot

    def res_choice(self, res_list, rule_type=''):
        if 'random' in rule_type:
            selectedResource = random.choice(res_list)
        elif 'FIFO' in rule_type:
            res_list.sort(key=lambda x: (x.lastWorkFinishTime + x.processingTimeInBuffer, x.resourceId))
            selectedResource = res_list[0]
        elif 'LIFO' in rule_type:
            res_list.sort(key=lambda x: (x.numOfPossibleProductType, x.resourceId))
            selectedResource = res_list[0]
        # SRO 고차우선 투입은 위의 FIFO와 동일하게 함
        else:
            res_list.sort(key=lambda x: (x.lastWorkFinishTime + x.processingTimeInBuffer, x.resourceId))
            selectedResource = res_list[0]
        return selectedResource
