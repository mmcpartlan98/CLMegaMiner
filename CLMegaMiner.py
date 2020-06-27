import math
import pickle
import requests
import datetime
import time
from lxml import html
import matplotlib.pyplot as plotter
from twilio.rest import Client

# Minutes between scraping
searchInterval = 1

# Twilio SMS API config
account_sid = 'AC8bd9f1713930d5c3a65e6ab592420dba'
auth_token = '82741da6122123696f5a4994a682f81d'
client = Client(account_sid, auth_token)


# Define craigslist listing object
class Listing:
    def __init__(self, title, link, price, listID):
        self.title = str(title.lower())
        self.link = link
        self.price = int(price[1:])
        self.listingID = listID
        # Try-catch block searches for more detail from each listing's specific page
        try:
            depthScrape = requests.get(self.link, timeout=10)
            subTree = html.fromstring(depthScrape.content)
            timeU = subTree.xpath(
                '/html/body/section/section/section/div[2]/p[3]/time[@class="date timeago"]/@datetime')
            timeP = subTree.xpath(
                '/html/body/section/section/section/div[2]/p[2]/time[@class="date timeago"]/@datetime')
            if len(timeU) == 0:
                if len(timeP) < 1:
                    print("                Time error! Marking post as deleted.")
                    self.title = "deleted"
                    print("Link to error page: ", self.link)
                    timeC = "2000-01-01 01:00:000"
                else:
                    timeC = timeP[0]
            else:
                timeC = timeU[0]
            self.listTime = datetime.datetime(int(timeC[0:4]), int(timeC[5:7]), int(timeC[8:10]), int(timeC[11:13]),
                                              int(timeC[14:16]), int(timeC[17:19]), 0)
            self.description = subTree.xpath('/html/body/section/section/section/section[@id="postingbody"]/text()['
                                             'normalize-space()]')

            # construct new list of strings for join function
            list_of_strings = [str(thing) for thing in self.description]
            self.description = "".join(list_of_strings)

            # Unclassified for now, may add in a future update
            self.classification = "Unclassified"

            # Collect all words in a listing, strip special characters, and store them as a string
            self.descriptiveText = str(self.title + self.description).replace(',', ' ').replace('\n', ' ').replace('.',
                                                                                                                   ' ')
            try:
                self.coverImageLink = str(subTree.xpath('/html/head/meta[9][@property="og:image"]/@content')[0])
            except IndexError as e:
                self.coverImageLink = "Unknown"

        except requests.exceptions.RequestException as e:
            print("Connection error:", e)
            self.listTime = "2000-01-01 01:00:000"
            self.description = "Could not retrieve item description!"
            self.classification = "Could not retrieve item classification!"


class Search:
    def __init__(self, location, searchTerms, keywordsPos, keyWordsNeg, minPrice, maxPrice):
        self.location = location
        self.searchTerms = searchTerms
        self.keywordsPos = keywordsPos + ' ' + searchTerms.replace('+', ' ')
        self.keywordsNeg = keyWordsNeg
        self.minPrice = minPrice
        self.maxPrice = maxPrice
        self.allObjects = list()
        self.hitObjects = list()

    def scrape(self, enableTexting):
        listingIndex = 0
        titles = list()
        links = list()
        prices = list()
        IDs = list()

        while True:
            try:
                r = requests.get("https://" + self.location + ".craigslist.org/search/sss?s=" + str(
                    listingIndex) + "&sort=date&query=" + self.searchTerms, timeout=10)
            except requests.exceptions.RequestException as e:
                print("Connection error:", e)
                return

            listingIndex = listingIndex + 120
            tree = html.fromstring(r.content)
            try:
                totalListings = int(
                    tree.xpath(
                        '/html/body/section/form/div[3]/div[3]/span[2]/span[3]/span[2][@class="totalcount"]/text()')[
                        0])
                shownListings = int(tree.xpath(
                    '/html/body/section/form/div[3]/div[3]/span[2]/span[3]/span[1]/span[2][@class="rangeTo"]/text()')[
                                        0])
            except IndexError as e:
                print("Index error: possible search timeout (10s timeout)", e)
                return

            titles.extend(tree.xpath('/html/body/section/form/div/ul/li/p/a[@class="result-title hdrlnk"]/text()'))
            links.extend(tree.xpath('/html/body/section/form/div/ul/li/p/a[@class="result-title hdrlnk"]/@href'))
            prices.extend(tree.xpath('/html/body/section/form/div/ul/li/p/span/span[@class="result-price"]/text()'))
            IDs.extend(tree.xpath('/html/body/section/form/div/ul/li[@class="result-row"]/@data-pid'))
            if shownListings == totalListings:
                break

        if len(prices) > totalListings:
            totalListings = len(prices)

        # Pre-filter results
        for i in range(len(prices)):
            print("        Checking", self.searchTerms.upper(), "-", self.location.upper(), i + 1, "/",
                  str(totalListings), "(", IDs[i], ")")
            if self.listingIsNew(IDs[i]):
                newListing = Listing(titles[i], links[i], prices[i], IDs[i])

                # Scoring using 'manual' identifiers
                self.allObjects.append(newListing)
                scoreReport = Search.scoreMatch(self.keywordsPos, self.keywordsNeg, newListing.descriptiveText)

                print("Found NEW listing! Score:", scoreReport)

                if scoreReport > 0.1 and newListing.title != "deleted":
                    if self.maxPrice >= newListing.price > self.minPrice:
                        self.hitObjects.append(newListing)
                        if enableTexting:
                            Search.sendText(newListing.price, newListing.link)

    def listingIsNew(self, listingID):
        status = True
        for thing in self.allObjects:
            if thing.listingID == listingID:
                status = False
        return status

    @staticmethod
    def sendText(price, link):
        print("TEXT SENT Price: $", price, link)
        message = client.messages.create(
            body=('Result: $' + str(price) + ' ' + str(link)),
            from_='+16076994438', to='+16509954172')
        print(message.sid)

    @staticmethod
    def scoreMatch(hotWords, coldWordsLocal, inString):
        badSymbols = ",./\\][!@#$%^&*()-=+_<>`~?\"\'"
        for symbol in badSymbols:
            inString.replace(symbol, ' ')
        stringWords = (inString.lower()).split()
        for word in stringWords:
            word.strip()

        hotWords = hotWords.split()
        coldWordsLocal = coldWordsLocal.split()
        hitScore = 0
        for word in stringWords:
            for checkWord in hotWords:
                if word == checkWord:
                    hitScore = hitScore + 1
            for checkWord in coldWordsLocal:
                if word == checkWord:
                    hitScore = hitScore - 10
        return hitScore / len(stringWords)


class MinerSearchObject:
    # A miner search object describes details of the search ONLY (no listing data is collected)
    # The preMine function does NOT actually search... it emulates cURL commands used to show Craigslist's
    # search result meta data before you actually run the search. It is believed that this is faster than a true search.
    def __init__(self, searchTerm, response):
        self.search = searchTerm
        self.results = response
        self.forSaleCount = 0
        try:
            splitResponse = self.results.split('"sss":{')[1].split('}')[0]
            splitResponse = splitResponse.split(',')

            for split in splitResponse:
                self.forSaleCount = self.forSaleCount + int(split.split(':')[1])
        except IndexError:
            pass


class DataMiner:
    def __init__(self, areaCode):
        self.areaCode = areaCode
        self.rangeStartIndex = self.areaCode * 1000000000
        self.rangeEndIndex = self.areaCode * 1000000000 + 999999999
        self.baseURL = "https://sfbay.craigslist.org/count-search?type=search-count&query="
        self.endURL = "&ordinal=1&ratio=0&clicked=0"

    class EmptyAttribute:
        def __init__(self):
            self.text = "{}"

    def preMine(self, startIndex, endIndex, interval, saveResults):
        runningTotal = 0
        fileName = str(startIndex) + '_' + str(endIndex) + '.pickle'

        IDDistResults = list()
        for index in range(math.floor(startIndex / interval), math.floor(endIndex / interval) + 1):
            if interval > 1:
                searchTermMiner = str(index) + "*"
            else:
                searchTermMiner = str(index)
            # Try to get the response twice before setting to empty string (to be interpreted as 0)
            try:
                queryResponse = requests.get(self.baseURL + searchTermMiner + self.endURL, timeout=10)
            except requests.exceptions.RequestException:
                try:
                    queryResponse = requests.get(self.baseURL + searchTermMiner + self.endURL, timeout=10)
                except requests.exceptions.RequestException:
                    return

            newResult = MinerSearchObject(searchTermMiner, queryResponse.text)

            IDDistResults.append(newResult)
            runningTotal = runningTotal + newResult.forSaleCount
            print(searchTermMiner, "        Produced ", newResult.forSaleCount, "for sale (sss) results.", "(",
                  runningTotal, ")")

            # Save after search completes
        if saveResults:
            with open(fileName, 'wb') as mineFile:
                print("Saving to file...")
                pickle.dump(IDDistResults, mineFile)
                print("Saved!")

    # Full sequential miner will eventually produce a collection of files that each contain one MinerSearchObject
    # for listing IDs confirmed to be valid. These files will be saved as LISTINGID.pickle. Other files with larger
    # ranges will be saved as well, but these are only used to find the 'hotspots' in the overall listing ID
    # distribution. Future versions of this software may even delete them automatically.
    #
    # The minListings parameter specifies the minimum valid listings per 100,000 possible IDs for the chunk to be
    # worth mining
    def fullSequentialMiner(self, minListings):
        try:
            try:
                # Attempt to load 'big' file with all listings
                with open(str(self.rangeStartIndex) + '_' + str(self.rangeEndIndex) + '.pickle', 'rb') as minedData:
                    IDDistResults = pickle.load(minedData)
                print("Successfully loaded previous distribution file!")
            except FileNotFoundError:
                # Otherwise, run preMine to make a new file, then use that one
                print("Unable to load previous distribution file! Creating a new one...")
                self.preMine(self.rangeStartIndex, self.rangeEndIndex, 100000, True)
                with open(str(self.rangeStartIndex) + '_' + str(self.rangeEndIndex) + '.pickle', 'rb') as minedData:
                    IDDistResults = pickle.load(minedData)

            listingDistribution = list()
            listingXVals = list()
            for item in IDDistResults:
                # Iterate through search terms
                listingDistribution.append(item.forSaleCount)
                # Turn the MinerSearchObject 'search' property into an indexible number
                listingXVals.append(int(item.search.split('*')[0]) * 100000)

            print("Beginning to mine...")

            for index in range(0, len(listingDistribution) - 1):
                if listingDistribution[index] >= minListings:
                    print(listingXVals[index], listingDistribution[index + 1])
                    try:
                        # If a file exists, use it
                        with open(str(listingXVals[index]) + '_' + str(listingXVals[index] + 99999) + '.pickle',
                                  'rb') as minedData:
                            IDDistResults = pickle.load(minedData)
                    except FileNotFoundError:
                        # Otherwise, run preMine to make a new file, then use that one
                        self.preMine(listingXVals[index], listingXVals[index] + 99999, 1000, True)
                        with open(str(listingXVals[index]) + '_' + str(listingXVals[index] + 99999) + '.pickle',
                                  'rb') as minedData:
                            IDDistResults = pickle.load(minedData)
                    for item in IDDistResults:
                        # Set threshold for third level of mining...
                        if item.forSaleCount > 50:
                            print("Launching third mining level...")
                            # Figure out the search range producing the hit, then search for individual listings
                            searchRangeMin = int(item.search.split('*')[0]) * 1000
                            searchRangeMax = searchRangeMin + 999
                            try:
                                # If a file exists, use it
                                with open(str(searchRangeMin) + '_' + str(searchRangeMax) + '.pickle',
                                          'rb') as minedData3:
                                    lowestLevelGrouping = pickle.load(minedData3)
                            except FileNotFoundError:
                                # Otherwise, run preMine to make a new file, then use that one
                                self.preMine(searchRangeMin, searchRangeMax, 10, True)
                                with open(str(searchRangeMin) + '_' + str(searchRangeMax) + '.pickle',
                                          'rb') as minedData3:
                                    lowestLevelGrouping = pickle.load(minedData3)

                            for subItem in lowestLevelGrouping:
                                if subItem.forSaleCount > 2:
                                    print("Collecting listing hits...")
                                    subSearchRangeMin = int(subItem.search.split('*')[0]) * 10
                                    subSearchRangeMax = subSearchRangeMin + 9
                                    try:
                                        # If a file exists, use it
                                        with open(str(subSearchRangeMin) + "_" + str(subSearchRangeMax) + '.pickle',
                                                  'rb') as minedData4:
                                            lowestLevelGrouping = pickle.load(minedData4)
                                    except FileNotFoundError:
                                        # Otherwise, run preMine to make a new file, then use that one
                                        self.preMine(subSearchRangeMin, subSearchRangeMax, 1, True)
                                        with open(str(subSearchRangeMin) + "_" + str(subSearchRangeMax) + '.pickle', 'rb') as minedData4:
                                            lowestLevelGrouping = pickle.load(minedData4)

        except TypeError as e:
            print(e)
            print("MAIN LOOP CRASH:")
            print("Loaded file is empty.")
            return

        except FileNotFoundError:
            print("MAIN LOOP CRASH:")
            print("No save file found.")
            return

        except pickle.UnpicklingError:
            print("MAIN LOOP CRASH:")
            print("Corrupt pickle file.")
            return

# Create the DataMiner object with area code 7
testDig = DataMiner(7)
# Run the full sequential miner to produce listing files
testDig.fullSequentialMiner(200)
