from copy import deepcopy as cp
from collections import defaultdict
from problemIO.lot import Lot


class Resource(object):
    # def __init__(self, resourceId, resourceModelId):
    #     self.resourceId = resourceId
    #     self.resourceModelId = resourceModelId

    # Default Constructor
    def __init__(self, resourceId, resourceModelId, operationId, resourceStatus, productInProcessed, lotIdProcessed,
                 setupStatus, setuped_operation):
        self.resourceId = resourceId
        self.resourceModelId = resourceModelId
        self.operationId = operationId

        self.resourceStatus = resourceStatus
        self.productIdProcessed = productInProcessed
        self.lotIdProcessed = lotIdProcessed
        self.resourceBuffer = []
        self.bufferSize = 1

        # For Setup Change
        self.lastWorkFinishTime = 0
        self.setupStartTime = []
        self.setupStatus = setupStatus  # MCP/2MCP_01/DA1
        self.setuped_operation = setuped_operation

        # For Sorting and Split
        self.processingTimeInBuffer = 0
        self.reservedLotId = ''

        # For History
        self.historyList = []

        # For DA Selection
        self.numOfPossibleProductType = 0

        # For Result
        self.total_idle_time = 0

    # Clone constructor 대신 이 함수를 사용
    def clone_resource(self):
        cloned_resource = cp(self)
        return cloned_resource

    def recordHistory(self, event, eventTime, toStatus, productIdProcessed, lotIdProcessed, lotOperationId,
                      lotPriorOperationId):

        fromEvent = ''
        duration = 0
        if len(self.historyList) > 0:
            prevResourceHistory = self.historyList[-1]
            duration = eventTime - prevResourceHistory.eventTime
            fromEvent = prevResourceHistory.event
        tempResourceHistory = ResourceHistory(self.resourceId, fromEvent, event, eventTime, self.resourceStatus, toStatus, self.operationId,
                                              lotPriorOperationId, lotOperationId, productIdProcessed, lotIdProcessed)
        tempResourceHistory.duration = duration

        self.historyList.append(tempResourceHistory)
        self.resourceStatus = toStatus
        self.productIdProcessed = productIdProcessed
        self.lotIdProcessed = lotIdProcessed

        if event == "START PROD":
            self.resourceBuffer.remove(lotIdProcessed)
            self.total_idle_time += tempResourceHistory.duration

    def getInfor(self):
        return "resourceId\t" + self.resourceId + "\n" + "resourceModelId\t" + self.resourceModelId + "\n" + "resourceStatus\t" + \
               self.resourceStatus + "\n" + "operationId\t" + self.operationId + "\n" + "productInProcessed\t" + \
               self.productIdProcessed + "\n" + "lotIdProcessed\t" + self.lotIdProcessed



""" ---------------------- Resource History ---------------------- """


class ResourceHistory(object):
    def __init__(self, resourceId, fromEvent, event, eventTime, fromStatus, toStatus, operationId, lotPriorOperationId,
                 lotOperationId, productIdProcessed, lotIdProcessed):
        self.resourceId = resourceId
        self.fromEvent = fromEvent
        self.event = event
        self.eventTime = eventTime
        self.fromStatus = fromStatus
        self.toStatus = toStatus
        self.operationId = operationId
        self.lotPriorOperationId = lotPriorOperationId
        self.lotOperationId = lotOperationId
        self.productIdProcessed = productIdProcessed
        self.lotIdProcessed = lotIdProcessed


""" -------------------- Resource Arrangement -------------------- """


class ResourceArrangement(object):
    def __init__(self,  id, opeId, resModel, prodId, processTime, processUnit, loadTime, unloadTime):
        self.resourceArrangementId = id
        self.operationId = opeId
        self.resourceModelId = resModel
        self.productId = prodId
        self.processingTime = processTime
        self.processingUnit = processUnit
        self.loadingTime = loadTime
        self.unloadingTime = unloadTime

    def getInfor(self):
        return "resourceArrangementId\t" + str(self.resourceArrangementId) + "\n" +"operationId\t" + self.operationId + "\n" +\
               "resourceModelId\t" + self.resourceModelId + "\n" + "productId\t" + self.productId + "\n" + "processingTime\t" + str(self.processingTime) + "\n" +\
               "processingUnit\t" + self.processingUnit + "\n" + "loadingTime\t" + str(self.loadingTime) + "\n" + "unloadingTime\t" + str(self.unloadingTime ) + "\n"


""" --------------------- Resource Model --------------------- """

class ResourceModel(object):
    def __init__(self, resourceModelId, operationId, arrangementMap):
        self.resourceModelId = resourceModelId
        self.operationId = operationId

        # Key: Product Code
        self.resourceArrangementMap = defaultdict(dict)  # default 값을 dict로 선언

        # Setup
        self.setupTime = {}

        for key, arrangement in arrangementMap.items():
            if arrangement.resourceModelId == self.resourceModelId:
                self.resourceArrangementMap[arrangement.productId][arrangement.operationId] = arrangement

    def setSetupTime (self, fromProduct, toProduct, time):
        key = fromProduct + "_" + toProduct
        self.setupTime[key] = time

    def getSetupTime(self, fromProduct, toProduct):
        key = fromProduct + "_" + toProduct
        return self.setupTime[key]

    def getInfor(self):
        msg = "resourceModelId\t" + self.resourceModelId + "\noperationId\t"+self.operationId+"\n"
        for p in self.resourceArrangementMap:
            for o in self.resourceArrangementMap[p]:
                ra = self.resourceArrangementMap[p][o]
                assert isinstance(ra, ResourceArrangement)
                msg += "<resource arrangement("+p+","+o+")>\n"+ra.getInfor()
        return msg

