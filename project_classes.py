
import datetime


class Transaction:
    """A class that represents a BOJ transaction for a single instrument on a single day\n
    Several transactions are usually conducted as part of a daily operation"""

    def __init__(self, instrument: str, currency: str, units: int):
        """Initializes the instance based on instrument, currency and units

        Args:
            instrument: the maturity category or instrument type being bought
            currency: the currency of the transaction, USD or JPY.
            units: the units of the transaction in millions (typically 100 for JPY, 1 for USD)

        """

        self._rate = None
        self._successful_bids = None
        self._competitive_bids = None
        self._ave_spread = None
        self._instrument = instrument
        self._currency = currency
        self._units = units

    @property
    def Rate(self) -> float:
        """The rate (yield) at which the transaction took place"""
        return self._rate

    @Rate.setter
    def Rate(self, rate: float):
        self._rate = rate

    @property
    def CompetitiveBids(self) -> int:
        """The value of competitive bids in auction method transactions"""
        return self._competitive_bids

    @CompetitiveBids.setter
    def CompetitiveBids(self, bids: int):
        self._competitive_bids = bids

    @property
    def SuccessfulBids(self) -> int:
        """The value of successful bids in auction method transactions"""
        return self._successful_bids

    @SuccessfulBids.setter
    def SuccessfulBids(self, bids: int):
        self._successful_bids = bids

    @property
    def AveSpread(self) -> float:
        """The average spread in auction method transactions, the yield in fixed-rate operations"""
        return self._ave_spread

    @AveSpread.setter
    def AveSpread(self, spread: float):
        self._ave_spread = spread

    @property
    def Instrument(self) -> str:
        """Returns the type of instrument involved in the transaction"""
        return self._instrument

    @property
    def Currency(self) -> str:
        """The currency of the transaction"""
        return self._currency

    @property
    def Units(self) -> int:
        """The units of the transaction"""
        return self._units


class Operation:
    """A class that represents a BOJ operation on a single day

    Several transactions are usually conducted as part of a daily operation"""

    def __init__(self, transdate: datetime.date):
        """Initializes the instance with a date

        Args:
            transdate: the date of the operation
        """
        self._date = transdate
        self._transactions = []

    @property
    def Date(self) -> datetime.date:
        """The date of the operation"""
        return self._date

    @Date.setter
    def Date(self, transdate: datetime.date):
        self._date = transdate

    def AddTransaction(self, instrument: str, currency: str, unit: int) -> object:
        """Adds a Transaction to the list of transactions in the current operation

        Args:
            instrument: the maturity category or instrument type being bought
            currency: the currency of the transaction, USD or JPY.
            unit: the units of the transaction in millions (typically 100 for JPY, 1 for USD)

        Returns:
            Transaction object: the added transaction

        """

        new_trans = Transaction(instrument, currency, unit)
        self._transactions.append(new_trans)
        return new_trans

    def DeleteTransaction(self, instrument: str) -> bool:
        """Removes a transaction from the list of transactions in the current operation

        Args:
            instrument: the maturity category or instrument type being bought

        Returns:
            bool: True if transaction found and removed, False if transaction not found

        """

        for trans in self._transactions:
            if trans.Instrument == instrument:
                # Delete from list
                self._transactions.remove(trans)
                return True
        return False

    @property
    def Transactions(self) -> list:
        """Returns a list of Transaction objects for the current operation"""

        return self._transactions

    @property
    def Instruments(self) -> list:
        """Returns a str list of instruments names"""

        instruments = []
        for trans in self._transactions:
            instruments.append(trans.Instrument)
        return instruments

    @property
    def TransactionsCount(self) -> int:
        """Returns the number of transactions in the operation"""
        return len(self._transactions)

    def Transaction(self, instrument: str) -> object:
        """Returns the transaction object for the named instrument

        Args:
            instrument: the name of the instrument

        Returns:
            Transaction object if found, None if object not found

        """

        for trans in self._transactions:
            if trans.Instrument == instrument:
                return trans
        return None

    def TransactionValue(self, instrument: str = None) -> float:
        """Returns the successful bid value for the instrument or the JPY total if no instrument given

        Args:
            instrument: the name of the requested instrument, leave blank for aggregation

        Returns:
            float: the value of successful transactions of an individual instrument\n
            or the aggregate value of all JPY transactions in the operation if instrument = None\n
            both values returned in units of bn

        """

        if instrument is not None:
            for trans in self._transactions:
                if trans.Instrument == instrument:
                    return (trans.SuccessfulBids * trans.Units) / 1000
        else:
            total = 0
            for trans in self._transactions:
                if trans.Instrument[0:3] == "JGB":
                    total += (trans.SuccessfulBids * trans.Units) / 1000
            return total
        return 0.0

    def TransactionRate(self, instrument: str) -> float:
        """The rate (yield) of the specified transaction

        Args:
            instrument: the name of the instrument

        Returns:
            float: the rate (yield) for the transaction of the requested instrument

        """

        for trans in self._transactions:
            if trans.Instrument == instrument:
                return trans.Rate
        return 0.0


