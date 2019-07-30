from copy import deepcopy as cp


class Lot(object):


    # # Clone Lot
    # def __init__(self, lot):
    #     self.lotId = lot.lotId
    #     self.productId = lot.productId
    #     self.flowId = lot.flowId
    #     self.flowNumber = lot.flowNumber
    #     self.lotStatus = lot.lotStatus
    #     self.lotQuantity = lot.lotQuantity
    #     self.UOMofQuantity = lot.UOMofQuantity
    #     self.currentOperationId = lot.currentOperationId
    #     self.currentResourceId = lot.currentResourceId
    #     self.currentOperationArrivalTime = lot.currentOperationArrivalTime
    #     self.currentOperationStartTime = lot.currentOperationStartTime
    #     self.factoryInTime = lot.factoryInTime
    #     self.lotLocation = lot.lotLocation
    #     self.lotPriority = lot.lotPriority
    #     self.lotDueDate = lot.lotDueDate

    # Default Constructor
    def __init__(self, lotId, productId, flowId, flowNumber, lotQuantity, lotPriority, lotDueDate, factoryInTime, lotLocation):
        # Inherited Information
        self.lotId = lotId
        self.productId = productId
        self.flowId = flowId
        self.lotQuantity = lotQuantity
        self.UOMofQuantity = "EA"
        self.lotPriority = lotPriority
        self.lotDueDate = lotDueDate
        self.factoryInTime = factoryInTime
        # Real Time Information
        self.flowNumber = flowNumber  # default: 1
        self.DA_flow_number = 0
        self.lotStatus = "WAIT"
        self.lotLocation = lotLocation
        self.currentOperationId = "DA1"
        self.currentResourceId = ""
        self.currentOperationArrivalTime = 0
        self.currentOperationStartTime = 0
        self.maxRemainingTime = 0
        # Sub Lot 관련 변수들
        self.subLotIdList = []
        # self.motherLotId = ""
        self.motherLot = None
        self.completedSubLot = 0
        # For History
        self.historyList = []
        self.reservationTimeRecord = {}  # 예약이 걸리는 시점
        self.reservedResourceIdRecord = {}  # 예약이 할당된 기계
        # For DA Selection
        self.feasibleResourceNum = 0
        self.activationValue = 0.0
        # For DA reserve & WB reserve
        self.reservedResourceId = ""
        # For DA Allocation - reservedResourceId로 통합 (170320)
        # self.allocatedResourceId = ""
        self.nowEvent = None

        # For DDW Reserve
        self.reservedSameResource = False

        # For rule
        self.processingTime = 0

    # Clone constructor 대신 이 함수를 사용
    def clone_lot(self):
        cloned_lot = cp(self)
        return cloned_lot

    def changeLotStatus(self, lotStatus, lotLocation = None, currentOperationId=None, currentResourceId=None, currentOperationArrivalTime=None, currentOperationStartTime=None):
        if lotLocation is None:
            lotLocation = self.lotLocation
        if currentOperationId is None:
            currentOperationId = self.currentOperationId
        if currentResourceId is None:
            currentResourceId = self.currentResourceId
        if currentOperationArrivalTime is None:
            currentOperationArrivalTime = self.currentOperationArrivalTime
        if currentOperationStartTime is None:
            currentOperationStartTime = self.currentOperationStartTime
        self.lotStatus = lotStatus
        self.lotLocation = lotLocation
        self.currentOperationId = currentOperationId
        self.currentResourceId = currentResourceId
        self.currentOperationArrivalTime = currentOperationArrivalTime
        self.currentOperationStartTime = currentOperationStartTime

    def setCurrentMaxRemainingTime(self, maxRemainingTime):
        self.maxRemainingTime = maxRemainingTime

    def setReservationRecord(self, operation, timestamp, resourceId):
        self.reservationTimeRecord[operation] = timestamp
        self.reservedResourceIdRecord[operation] = resourceId
        self.reservedResourceId = resourceId

    """
    motherLotId -> motherLot을 저장, lotMap을 넘기지 않아도 된다.
    toLotStatus/toOpe/toLoc/toResource를 현재 lot의 값을 default로 사용하여 인수를 최소화 한다
    """

    def recordHistory(self, event, eventTime, toLotStatus = None, toLocationId = None, toResourceId = None, toOperationId = None, motherLot = None, lossQuantity = 0):
        # 기존값으로 Default값 부여
        if toLotStatus is None:
            toLotStatus = self.lotStatus
        if toOperationId is None:
            toOperationId = self.currentOperationId
        if toLocationId is None:
            toLocationId = self.lotLocation
        if toResourceId is None:
            toResourceId = self.currentResourceId
        if motherLot is None:
            motherLot = self.motherLot

        self.lotQuantity = self.lotQuantity - lossQuantity

        if  event == "SPLIT"  or  event == "MERGE":
            self.UOMofQuantity = "LOT"
        elif toOperationId == "MD":
            self.UOMofQuantity = "LOT"
        else:
            self.UOMofQuantity = "EA"
        toLocationIdForHistory = toLocationId
        if "WAY" in toLocationId:
            toLocationIdForHistory = toLocationId[7:]

        fromEvent = ''
        duration = 0
        motherLotId = ''
        if motherLot is not None:
            motherLotId = motherLot.lotId
        if len(self.historyList) > 0:
            prevLotHistory = self.historyList[-1]
            duration = eventTime - prevLotHistory.eventTime
            fromEvent = prevLotHistory.event
        tempLotHistory = LotHistory(self.lotId, self.productId, self.currentOperationId, self.lotQuantity,
                                    lossQuantity, self.UOMofQuantity, fromEvent, event, eventTime, self.lotStatus, toLotStatus,
                                    self.currentOperationId, toOperationId, toLocationIdForHistory, toResourceId, motherLotId)
        tempLotHistory.duration = duration

        if len(self.historyList) == 0:
            # Sub Lot의 생성
            if motherLot is not None:
                lastEventTime = 0
                if  len(motherLot.historyList) <= 1:  # Hot start 상황
                    pass
                else:
                    motherLotLastHistory = motherLot.historyList[-1]
                    lastEventTime = motherLotLastHistory.eventTime
                tempLotHistory.duration = eventTime - lastEventTime

            # 최초의 Event 발생.Factory In -> Move
            else:
                tempLotHistory.duration = eventTime - self.factoryInTime

        if event == "TRACK IN":
            if self.currentOperationId in self.reservationTimeRecord:
                reservationTime = self.reservationTimeRecord[self.currentOperationId]
                # 지금 막 생성한 History에 reservation되었던 시간을 함께 넣어줌
                tempLotHistory.setReservationTime(reservationTime)
        self.historyList.append(tempLotHistory)
        self.lotStatus = toLotStatus
        self.currentOperationId = toOperationId
        self.currentResourceId = toResourceId
        self.lotLocation = toLocationId
        self.motherLot = motherLot

        """
        Move 전에 Track out 됐을 때 이미 처리됨. 여기서추가로 할 필요 없음
        Strat 역시 다른 함수에서 바꾸므로 여기서 업데이트 할 필요가 없음
        self.currentOperationArrivalTime = eventTime
        self.currentOperationStartTime = eventTime
        """


        """
        duration 구 버전
         if (event.equals("TRACK OUT") & & self.motherLotId.length() > 0){
         tempLotHistory.duration = 900
         LotHistory prevLotHistory = historyList.get(historyList.size()-1)
         prevLotHistory.duration = eventTime - prevLotHistory.eventTime
            }
                else if(event.equals("MERGE")){
         if (historyList.size() > 0){
         LotHistory prevLotHistory = historyList.get(historyList.size()-1)
             prevLotHistory.duration = 900
                }
                }
                else{
                 if(historyList.size( ) >0){
                        LotHistory prevLotHistory = historyList.get(historyList.size()-1)
                        prevLotHistory.duration = eventTime - prevLotHistory.eventTime
                    }
                }
        """


    def mergeLot(self):
        self.subLotIdList = []

    def getInfor(self):
        return "lotId\t" + self.lotId + "\n"+ "productId\t" + self.productId+ "\n"+"flowId\t" + self.flowId + \
                    "\n" + "lotStatus\t"+self.lotStatus +"\n"+"lotQuantity\t"+str(self.lotQuantity) + "\n" + "factoryInTime\t" + str(self.factoryInTime) + "\n" + \
                    "lotLocation\t" + self.lotLocation + "\n" + "lotPriority\t" + str(self.lotPriority)+ "\n" +"dueDate\t" + str(self.lotDueDate)

""" ---------------------- Lot History ---------------------- """
class LotHistory(object):
    def __init__(self,  lotId,  productId,  operationId,  quantity, lossQuantity, UOMofQuantity,  fromEvent,  event,
                 eventTime,  fromStatus,  toStatus, fromOperationId,  toOperationId,  toLocationId,  toResourceId, motherLotId):
        self.lotId = lotId
        self.productId = productId
        self.operationId = operationId
        self.quantity = quantity
        self.lossQuantity = lossQuantity
        self.UOMofQuantity = UOMofQuantity
        self.fromEvent = fromEvent
        self.event = event
        self.eventTime = eventTime
        self.fromStatus = fromStatus
        self.toStatus = toStatus
        self.fromOperationId = fromOperationId
        self.toOperationId = toOperationId
        self.toLocationId = toLocationId
        self.toResourceId = toResourceId
        self.motherLotId = motherLotId
        self.reservationTime = -1
        self.duration = 0

    def setReservationTime(self, timestamp):
        self.reservationTime = timestamp
