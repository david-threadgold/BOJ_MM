# -*- coding: utf-8 -*-

"""
Created on Sat Feb 18 09:23:02 2023

@author: ThreadgoldDavid
"""

import os
import sys
import datetime
from datetime import timedelta, date
import requests
import urllib.error
import pandas as pd
import numpy as np
from dateutil.relativedelta import relativedelta
import re
from collections import OrderedDict
from project_classes import Operation
import matplotlib
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from pypdf import PdfMerger
import json


DAYS = 1050  # Number of days to go back
OUTPUT_PAGES = 2
JSON_FILE = r"BOJ_Ops.json"


def main():
    """main function to:

    (1) ask user if he wishes to use JSON data or refresh that data from the BOJ website\n
    (2) if refresh requested to load data from BOJ website from two source\n
    (a) monthly Excel files\n
    (b) daily web pages\n
    (3) clean up the retrieved data and populate a list of Operation classes each with Transaction subclasses\n
    (4) save the data to a JSON file, alternatively load the existing JSON data and create the list of Operation classes\n
    (5) create 2 pdf pages each with 3 matplotlib charts of the BOJ transaction data\n
    (6) combine the 2 pdfs into a single 2-page pdf

    """

    print("Getting BOJ Money Market Operations")

    # stop warnings for chained assignments
    pd.options.mode.chained_assignment = None

    operations = []
    reply = "Y"

    # If there is a backup JSON file give user the opportunity to use it
    if os.path.isfile(JSON_FILE):
        operations = load_from_json(JSON_FILE)
        if len(operations) > 0:
            start_date = operations[0].Date
            end_date_web = operations[-1].Date
            how_old = (date.today() - end_date_web).days
            while True:
                message = (
                    "\nLoad new data from BOJ or reload backup (Y/N)\n"
                    + "Backup may be up to {} days old\n".format(how_old)
                    + "Enter Y to refresh data or N to use stored data\n"
                )
                reply = input(message).upper()
                if reply == "N" or reply == "Y":
                    break

    # Otherwise get data from BOK website
    if reply != "N":
        # Set first and last dates for data retrival
        # We'll use Excel data until the end of the month two months ago
        # After that until today
        start_date = date.today() + relativedelta(days=-DAYS)
        start_date_excel = date(start_date.year, start_date.month, 1)
        end_date_excel = date.today() + relativedelta(months=-2)
        end_date_excel = date(end_date_excel.year, end_date_excel.month, 1)
        start_date_web = end_date_excel + relativedelta(months=1)
        end_date_web = date.today()
        total_days = (end_date_web - start_date_excel).days + 1

        # Read the BOJ's Excel files for historical transactions
        new_ops = get_historical_excel_data(start_date_excel, end_date_excel, total_days)
        # Append result to list of operations
        operations.extend(new_ops)

        # Reset progress bar
        progress = (start_date_web - start_date_excel).days + 1

        # Read the more recent data from the web pages
        new_ops = get_web_data(start_date_web, end_date_web, progress, total_days)
        # Append result to list of operations

        operations.extend(new_ops)

        result = save_to_json(operations, JSON_FILE)
        if result:
            print("Data saved to file")
        else:
            print("File operation failed, data not saved")

    select_generate_charts(operations, start_date, end_date_web)


def daterange(start_date: datetime.date, end_date: datetime.date) -> datetime.date:
    """Get dates one by one over a date range

    Args:
        start_date: the first date in the date\n
        end_date: the last date in the range

    """

    for n in range(int((end_date - start_date).days) ):
        yield start_date + timedelta(n)


def clean_up_notes(df_notes: pd.DataFrame, date: datetime.date) -> pd.DataFrame:
    """Extract fixed-rate operations details from notes section of webpage

    Args:
        df_notes: the unprocessed dataframe containing the notes to the daily operation\n
        date: the date of the operation

    Returns:
        DataFrame: a three column dataframe with date, rate, and instrument columns

    """

    # Set up dataframe with three columes with
    # first containing lines from transaction notes
    df_notes.columns = ["Note"]
    df_notes["Maturity"] = ""
    df_notes["Rate"] = ""

    # Iterate over rows, extract maturity and yield values,
    # insert nan if not present
    for index, i in enumerate(df_notes["Note"]):
        maturity_rate = re.match(r".+ Bank's purchasing yield of ([0-9]?[0-9])-year JGB .+ at ([0-9]\.[0-9][0-9][0-9])\%.+", i)
        if not maturity_rate:
            # No match, so set to "nan/nat"
            df_notes["Note"][index] = pd.NaT
        else:
            # Add the maturity and yield data to the dataframe
            df_notes["Maturity"][index] = int(maturity_rate.group(1).strip())
            df_notes["Rate"][index] = float(maturity_rate.group(2).strip())

    # Remove rows that do not have maturity and yield values
    df_notes.dropna(subset=["Note"], inplace=True)

    # Remove "Notes" column and eliminate duplicates
    df_notes = df_notes.drop("Note", axis=1)
    df_notes = df_notes.drop_duplicates()

    # Add date column and return
    df_notes["Date"] = date
    return df_notes


def clean_up_data(df_data: pd.DataFrame, date: datetime.date) -> pd.DataFrame:
    """Replace transaction names with short names and aggregate over similar instruments

    Args:
        df_data: the unprocessed dataframe\n
        date: the date of the operation

    Returns:
        DataFrame: a 4 column dataframe

    """

    # Remove unnecessary columns
    df_data = df_data[[0, 1, 2, 5]]
    df_data.columns = [
        "Instrument",
        "Competitive Bids",
        "Successful Bids",
        "Successful Yield",
    ]

    # Convert long names from BOJ to our short names
    for index, i in enumerate(df_data["Instrument"]):
        df_data["Instrument"][index] = get_short_name(i)

    # Aggrigate items as we don't need information on specific bonds etc
    df_data = df_data.fillna(0)
    df_data = df_data.groupby("Instrument").sum()

    # Add date and reset index
    df_data["Date"] = date
    df_data.reset_index(drop=False, inplace=True)

    return df_data


def get_short_name(long_name: str) -> str:
    """Replace long names used on BOJ website with short alternatives

    Args:
        long_name: the original instrument name\n

    Returns:
        str: the short name

    """

    # Dictionary of simple search terms, order is important
    searches = OrderedDict()
    searches[r"Outright purchases of Corporate Bonds"] = "Corporate Bonds"
    searches[r"Outright purchases of CP"] = "CP"
    searches[r"Outright purchases of T-Bills"] = "TB"
    searches[r"inflation-indexed bonds"] = "JGBs: Inflation Linked"
    searches[r"floating-rate bonds"] = "JGBs: Floating Rate"
    searches[r"US Dollar Funds-Supplying Operations against Pooled Collateral \(Sales of JGSs under repurchase agreements\)"] = "USD: JGS PC"
    searches[r"US Dollar Funds-Supplying Operations against Pooled Collateral"] = "USD: PC"
    searches[r"Funds-Supplying Operations against Pooled Collateral \(at All Offices\)"] = "Funds-Supplying Operations"

    # Iterate through dict, return immediately if match found
    for s, r in searches.items():
        if re.findall(s, long_name, re.IGNORECASE):
            return r

    # Parse out maturities for both conventional and fixed rate operations
    for trans_type in ["fixed", "floating"]:
        # Base text good for both fixed and floating
        re_txt = "maturity of (?:more than ([0-9]?[0-9]) years?\)?)?(?:(?:.+)?up to ([0-9]?[0-9]) years?\))?"
        out_txt = "JGBs: "
        if trans_type == "fixed":
            # Add in specific text for fixed rate operations
            re_txt = "\(fixed-rate method\) .+ " + re_txt
            out_txt = out_txt + "FR "

        # Perform seach
        maturity_rate = re.match(r".+ " + re_txt, long_name, re.IGNORECASE)
        if maturity_rate:
            # If only greater than clause matched
            if maturity_rate.group(2) == None:
                name = out_txt + ">" + maturity_rate.group(1) + "y"
            # If only less than clause match
            elif maturity_rate.group(1) == None:
                name = out_txt + "<" + maturity_rate.group(2) + "y"
            # Both clauses found matches
            else:
                name = out_txt + maturity_rate.group(1) + "-" + maturity_rate.group(2) + "y"
            return name

    # Get REPOs for morning and afternoon
    maturity_rate = re.match(r".+ \(Sales of JGSs under repurchase agreements\) /offered in the (.+)/.+", long_name, re.IGNORECASE)
    if maturity_rate:
        if maturity_rate.group(1) == "morning":
            name = "Sec. lending: am"
        elif maturity_rate.group(1) == "afternoon":
            name = "Sec. lending: pm"
        else:
            raise ValueError("Expected morning / afternoon flag not found")
        return name

    # If we haven't found a match return error
    raise ValueError("Imstrument not recognized: " + long_name)


def add_operation(curdate, df_data: pd.DataFrame, df_notes: pd.DataFrame = None) -> type[Operation]:
    """Add details of an operation to a new Operation object and return it

    Args:
        curdate: the date of the operation\n
        df_data: a dataframe of transactions on that date\n
        df_notes: a dataframe of details for fixed-rate transactions

    Returns:
        Operation object: an Operation object containing transactions in the current operation

    """

    new_op = Operation(curdate)

    # Iterate though the list of transactions and add to the operation class
    for index, row in df_data.iterrows():
        if row["Instrument"][0:3] == "USD":
            currency = "USD"
            unit = 1
        else:
            currency = "JPY"
            unit = 100
        newTrans = new_op.AddTransaction(row["Instrument"], currency, unit)
        newTrans.CompetitiveBids = int(row["Competitive Bids"])
        newTrans.SuccessfulBids = int(row["Successful Bids"])
        newTrans.Rate = float(row["Successful Yield"])

    # For fixed rate operations we need to add in the rate from the "Notes"
    if df_notes is not None:
        for index, row in df_notes.iterrows():
            # Add rates for fixed rate operations
            maturity = row["Maturity"]
            if maturity == 5:
                instrument = "JGBs: FR 3-5y"
            elif maturity == 2:
                instrument = "JGBs: FR 1-3y"
            elif maturity == 10:
                instrument = "JGBs: FR 5-10y"
            elif maturity == 20:
                instrument = "JGBs: FR 10-25y"
            else:
                raise ValueError("Unrecognized fixed rate operation maturity")

            newTrans = new_op.Transaction(instrument)
            if newTrans is None:
                raise ValueError("Unrecognized fixed rate operation maturity")
            else:
                newTrans.Rate = float(row["Rate"])
    return new_op


def add_operations(df_data: pd.DataFrame) -> list:
    """Create multiple Operation objects and return as a list of Operations

    Args:
        df_data: a dataframe listing multiple operations and transactions over multiple days

    Returns:
        list: a list of Operation objects, each member an Operation object for a single day

    """

    new_ops = []
    dates = df_data["Date"].unique()
    for curdate in dates:
        df_oneday = df_data.loc[df_data["Date"].isin([curdate])]
        new_op = add_operation(curdate, df_oneday)
        new_ops.append(new_op)
    return new_ops


def get_excel_data(file_date: datetime.date) -> pd.DataFrame:
    """Open and read monthly Excel files from BOJ

    Args:
        file_date: datetime.date for the first day of the target month

    Return:
        dataframe: a dataframe containing all operations and transactions during the month

    """

    try:
        file_ad = r"https://www.boj.or.jp/en/statistics/boj/fm/ope/m_release/{}/ope{}.xlsx".format(file_date.strftime("%Y"), file_date.strftime("%y%m"))
        df = pd.read_excel(
            file_ad,
            sheet_name="ope1",
        )
    except (AttributeError, urllib.error.HTTPError):
        print("\nUnable to retrieve Excel for " + file_date.strftime("%B %Y") + "\n")
        return None

    # File is poorly formatted, need to find start and end of tables
    # Do this by finding first and last instance of integer in "Competitive Bids" column
    start = 0
    stop = 0
    starts = []
    FRM = 0
    for index, row in df.iterrows():
        title = str(row[0]).lower()
        if "(fixed-rate method)" in title:
            FRM = index
        if not start and isinstance(row[4], int):
            start = index
        if start and isinstance(row[4], int) == False:
            stop = index - 1
            start_stop = (start, stop)
            starts.append(start_stop)
            start = 0
            stop = 0
    # Extract first table which is for JGB purchases under auction method
    # Did not find table for auction method (should be nine rows between title and start of data)
    df_data = df.iloc[starts[0][0] : starts[0][1]]

    # Table has changed to add new columns, so need to check number of columns
    shape = df_data.shape
    if shape[1] == 13:
        df_data = df_data.iloc[:, [0, 4, 5, 8, 11]]
    elif shape[1] == 11:
        df_data = df_data.iloc[:, [0, 3, 4, 7, 10]]
    else:
        raise ValueError("Shape not recognized")
    df_data.columns = ["Date", "Competitive Bids", "Successful Bids", "Successful Yield", "Instrument"]

    # Iterate over table, converts Excel date number to Datetime value and fill in short names for Instruments
    for index, row in df_data.iterrows():
        if isinstance(df_data["Date"][index], datetime.datetime) == False:
            df_data["Date"][index] = datetime.datetime.fromtimestamp((df_data["Date"][index] - 25569) * 86400).date()
        else:
            df_data["Date"][index] = df_data["Date"][index].date()
        long_name = df_data["Instrument"][index]
        more_than = re.match(r"^More than ([0-9]?[0-9]) years?", long_name, re.IGNORECASE)
        less_than = re.match(r"(?:.+)?up to ([0-9]?[0-9]) years?", long_name, re.IGNORECASE)
        if not more_than:
            new_name = "JGBs: <" + less_than.group(1) + "y"
        elif not less_than:
            new_name = "JGBs: >" + more_than.group(1) + "y"
        else:
            new_name = "JGBs: " + more_than.group(1) + "-" + less_than.group(1) + "y"
        df_data["Instrument"][index] = new_name

    # Aggregate values by day, Instrument
    df_data = df_data.fillna(0)
    df_data = df_data.groupby(["Date", "Instrument"]).sum()
    df_data = df_data.reset_index()

    # Check if fixed-rate table exists
    if len(starts) < 2:
        # Only one table found
        df_notes = None
    elif starts[1][0] - FRM != 9:
        # Did not find fixed-rates table title (9 rows between title and table)
        df_notes = None
    else:
        # Iterate over table, converts Excel date number to Datetime value and fill in short names for Instruments
        # Extract the second table which is for JGB purchases under fixed-rate method
        df_notes = df.iloc[starts[1][0] : starts[1][1]]
        df_notes = df_notes.iloc[:, [0, 4, 5, 8, 12]]
        df_notes.columns = ["Date", "Competitive Bids", "Successful Bids", "Successful Yield", "Instrument"]
        for index, row in df_notes.iterrows():
            if isinstance(df_notes["Date"][index], datetime.datetime) == False:
                df_notes["Date"][index] = datetime.datetime.fromtimestamp((df_notes["Date"][index] - 25569) * 86400).date()
            else:
                df_notes["Date"][index] = df_notes["Date"][index].date()
            mat_rate = re.match(r"^([0-9]?[0-9])-year JGB .+ : ([0-9].[0-9][0-9][0-9])%$", df_notes["Instrument"][index], re.IGNORECASE)
            # Add rates for fixed rate operations
            maturity = int(mat_rate.group(1))
            if maturity == 5:
                instrument = "JGBs: FR 3-5y"
            elif maturity == 2:
                instrument = "JGBs: FR 1-3y"
            elif maturity == 10:
                instrument = "JGBs: FR 5-10y"
            elif maturity == 20:
                instrument = "JGBs: FR 10-25y"
            else:
                raise ValueError("Unrecognized fixed rate operation maturity")
            df_notes["Instrument"][index] = instrument
            df_notes["Successful Yield"][index] = mat_rate.group(2)

        # Aggregate values by day, Instrument, and yield (we don't want to aggregate yields)
        df_notes = df_notes.fillna(0)
        df_notes = df_notes.groupby(["Date", "Successful Yield", "Instrument"]).sum()
        df_notes = df_notes.reset_index()
        df_notes = df_notes[["Date", "Instrument", "Competitive Bids", "Successful Bids", "Successful Yield"]]

    # if the df_notes dataframe exists append it to the df_data dataframe and return the result sorted by date
    if df_notes is not None:
        df_full = pd.concat([df_data, df_notes])
    else:
        df_full = df_data
    df_full = df_full.sort_values("Date")
    df_full.reset_index(drop=True, inplace=True)
    return df_full


def get_historical_excel_data(start_date: datetime.date, end_date: datetime.date, progress_total: int) -> list:
    """Retrieve Excel data from multiple monthly files and return list of Operation objects

    Args:
        start_date: start month/year\n
        end_date: end month/year\n
        progress_total: int, the total number of days in the operation, including Excel data retrieval

    Returns:
        list: a list of Operations objects, one for each day in the requested priod

    """

    ops = []
    month_list = [i for i in pd.date_range(start=start_date, end=end_date, freq="MS")]
    for month in month_list:
        days = (month.date() - start_date).days
        progress = float(days / progress_total)
        update_progress(progress, "Getting Excel data:")
        df_full = get_excel_data(month)
        if df_full is not None:
            new_ops = add_operations(df_full)
            ops.extend(new_ops)
    return ops


def get_web_data(start_date: datetime.date, end_date: datetime.date, progress_start: int, progress_total) -> list:
    """Retrieve web page data from multiple daily operations pages and return list of Operation objects

    Args:
        start_date: start month/year\n
        end_date: end month/year\n
        progress_total: int, the total number of days in the operation, including Excel data retrieval

    Returns:
        list: a list of Operations objects, one for each day in the requested priod

    """

    ops = []
    for curdate in daterange(start_date, end_date + relativedelta(days=1)):
        # Update progress bar
        if progress_total > 0:
            update_progress(progress_start / progress_total, "Getting web data: ")
            progress_start += 1

        # BOJ has separate pages for Offers and Results for each day
        url = r"https://www3.boj.or.jp/market/en/stat/ba{}.htm".format(curdate.strftime("%y%m%d"))
        url_of = r"https://www3.boj.or.jp/market/en/stat/of{}.htm".format(curdate.strftime("%y%m%d"))
        html = requests.get(url).content
        try:
            df_list = pd.read_html(html)
        except (ValueError, ImportError):
            # If the page doesn't exist (eg weekend / results not yet released) skip to next date
            continue

        # Translaction data is in the first list
        # Get it and clean it up
        df_data = df_list[1]
        df_data = clean_up_data(df_data, curdate)

        # Notes contain information on fixed rate operations but only on "Offers" page
        html = requests.get(url_of).content
        try:
            df_list = pd.read_html(html)
        except ImportError:
            sys.exit("Unable to find offer page for results page")
        df_notes = df_list[2]
        df_notes = clean_up_notes(df_notes, curdate)

        # Create class objects
        new_op = add_operation(curdate, df_data, df_notes)
        ops.append(new_op)
    return ops


def get_chart_data(
    operations: list, instruments: list, start_date: datetime.date, end_date: datetime.date, rate: bool = False, monthly: bool = True
) -> pd.DataFrame:
    """Get set of data for a chart,

    Args:
        operations: list of Operations objects\n
        instruments: list of str. Names of the required instruments\n
        start_date: start month/year\n
        end_date: end month/year\n
        rate: chart rate (yield) if True, successful bids if False. Default = False\n
        monthly: aggregate data by month if True, daily if False. Default = False

    Returns:
        dataframe: dataframe with columns for date and value of each instrument

    """

    # Can request aggregate for all JGBs with the "All" instrument
    if "All" in instruments:
        inst_filter = [
            "JGBs: FR 5-10y",
            "JGBs: FR 1-3y",
            "JGBs: FR 3-5y",
            "JGBs: FR 10-25y",
            "JGBs: <1y",
            "JGBs: 1-3y",
            "JGBs: 3-5y",
            "JGBs: 5-10y",
            "JGBs: 10-25y",
            "JGBs: >25y",
            "JGBs: Inflation Linked",
        ]
        # Create list of unique values that includes all JGBs as well as any other requested items
        inst_filter = list(set(inst_filter) | set(instruments))

        # can't get a rate for an aggregate so set rate to False
        rate = False
    else:
        inst_filter = instruments

    # Filter opeartions list to only those dates in requested range that have data for at least one of the requested instruments
    ops = [op for op in operations if ((op.Date >= start_date and op.Date <= end_date) and (any(inst in inst_filter for inst in op.Instruments)))]

    # Extract the list of dates
    ops_dates = [op.Date for op in ops]

    # Get values for each of the requested instruments
    ops_values = []
    for inst in instruments:
        if rate:
            values = [op.TransactionRate(inst) for op in ops]
        else:
            if inst == "All":
                # Omitting instrument name will return value for all JGBs
                values = [op.TransactionValue() for op in ops]
            else:
                values = [op.TransactionValue(inst) for op in ops]
        ops_values.append(values)

    # Transpose the values array so columns the instruments
    ops_values = np.array(ops_values).T.tolist()

    # Build return dataframe starting with Dates
    df_return = pd.DataFrame(list(ops_dates), columns=["Date"])

    # Add in values for each requested instrument
    for index, inst in enumerate(instruments):
        df_return[inst] = [ops_value[index] for ops_value in ops_values]

    # Aggreate monthly data if flag set, if rate use mean value
    if monthly:
        df_return["Date"] = [date(x.year, x.month, 1) for x in df_return["Date"]]
        if rate:
            df_return = df_return.groupby(["Date"]).mean()
        else:
            df_return = df_return.groupby(["Date"]).sum()
        df_return = df_return.reset_index()

    return df_return


def select_generate_charts(operations: list, start_date: datetime.date, end_date: datetime.date) -> bool:
    """Sets parameters for the charts to be plotted and combine the output pdf files

    Args:
        operations: a list of Operations objects\n
        start_date: plot from this date\n
        end_date: plot until this date

    Returns:
        bool: True if succeed, False if fail

    """

    print("Preparing PDF")

    # Choose data to be plotted and types of charts
    # Bar chart for aution purchases monthly
    chart_data_1 = get_chart_data(
        operations, ["JGBs: <1y", "JGBs: 1-3y", "JGBs: 3-5y", "JGBs: 5-10y", "JGBs: 10-25y", "JGBs: >25y"], start_date, end_date, False, True
    )

    # Bar chart for fixed-rate purchases monthly
    chart_data_2 = get_chart_data(operations, ["JGBs: FR 1-3y", "JGBs: FR 3-5y", "JGBs: FR 5-10y", "JGBs: FR 10-25y"], start_date, end_date, False, True)

    # Line chart for all purchases
    chart_data_3 = get_chart_data(operations, ["All"], start_date, end_date, False, True)

    # Scatter chart for auction purchases daily
    chart_data_4 = get_chart_data(
        operations, ["JGBs: <1y", "JGBs: 1-3y", "JGBs: 3-5y", "JGBs: 5-10y", "JGBs: 10-25y", "JGBs: >25y"], start_date, end_date, False, False
    )

    # Scatter chart for fixed rate purchases daily
    chart_data_5 = get_chart_data(operations, ["JGBs: FR 1-3y", "JGBs: FR 3-5y", "JGBs: FR 5-10y", "JGBs: FR 10-25y"], start_date, end_date, False, False)

    # Scatter chart for rates on fixed-rate purchases daily
    chart_data_6 = get_chart_data(operations, ["JGBs: FR 1-3y", "JGBs: FR 3-5y", "JGBs: FR 5-10y", "JGBs: FR 10-25y"], start_date, end_date, True, False)

    # Plot first page of charts
    plot_charts(
        [chart_data_1, chart_data_2, chart_data_3],
        ["bar", "bar", "line"],
        [
            "BOJ auction purchases of JGBs, monthly ¥bn",
            "BOJ fixed-rate purchases of JGBs, monthly ¥bn",
            "All BOJ JPY operations, monthly ¥bn",
        ],
        [False, False, False],
        1,
    )

    # Plot second page of charts
    plot_charts(
        [chart_data_4, chart_data_5, chart_data_6],
        ["scatter", "scatter", "scatter"],
        ["BOJ auction purchases of JGBs, daily ¥bn", "BOJ fixed-rate purchases of JGBs, daily ¥bn", "Rate for fixed-rate operations, daily %"],
        [False, False, True],
        2,
    )

    # Combine pdfs
    merger = PdfMerger()
    for i in range(OUTPUT_PAGES):
        try:
            merger.append(r"BOJ_plot_{}.pdf".format(i + 1))
        except FileNotFoundError:
            print("Unable to find PDF file")
            return False
    merger.write(r"BOJ_plot.pdf")
    merger.close()

    # Remove single page PDFs
    for i in range(OUTPUT_PAGES):
        try:
            os.remove(r"BOJ_plot_{}.pdf".format(i + 1))
        except (FileNotFoundError, PermissionError):
            print("Unable to find PDF file")
            return False

    print("PDF created")
    return True


def plot_charts(chart_data: list, chart_types: list, titles: list, rates: list, page: int = 1):
    """Plot multiple series with Matplotlib and save as pdf

    Args:
        chart_data: a list of dataframes with the data for each chart\n
        chart_types: a list of str of the chart types (Bar, Scatter, Line)\n
        titles: a list of str of the titles for the charts\n
        rates: a list of bool: True if rate (yield) is plotted, False if successful bids\n
        page: int page number in final pdf

    """

    # Earch argument is a list of elements for each chart, list lengths much be equal
    colors = ["#242852", "#C00000", "#5AA2AE", "#FFC000", "#ACCBF9", "#00B050"]
    plots = len(titles)

    # Check each argument is of the same length, equivalent to the number of charts to be plotted
    if len(chart_data) != plots or len(chart_types) != plots or len(rates) != plots:
        raise ValueError("All arguments passed to plot_charts function much be of the same length")

    # Set up plot, size gives A4, portrait
    fig, ax = plt.subplots(plots, 1, figsize=(8.15, 3.86 * plots), layout="constrained")

    # Iterate over the parameters for each chart
    for i in range(plots):
        chart_type = chart_types[i]
        rate = rates[i]
        title = titles[i]
        df_data = chart_data[i]
        insts = list(df_data.columns)

        start_date = df_data["Date"][0]
        end_date = df_data["Date"][df_data.shape[0] - 1]
        days = (end_date - start_date).days
        if days > 2000:
            interval = 6
        elif days > 500:
            interval = 3
        else:
            interval = 1

        if chart_type == "bar":
            # Aggregate bars in reverse order to create stacked bar chart
            # Reformat date to use a bar lables on x-axis or set format for line / scatter charts
            for j in range(len(insts) - 1, 1, -1):
                df_data.loc[:, insts[j - 1]] = df_data.loc[:, insts[j - 1]].add(df_data.loc[:, insts[j]])
            df_data["Date"] = pd.to_datetime(df_data["Date"]).dt.strftime("%y/%m")
        else:
            ax[i].xaxis.set_major_formatter(mdates.DateFormatter("%y/%m"))
            ax[i].xaxis.set_major_locator(mdates.MonthLocator(interval=interval))

        for j in range(len(insts) - 1):
            df_data.plot(kind=chart_type, x="Date", y=insts[j + 1], color=colors[j], ax=ax[i], label=insts[j + 1])

        # Format axis and legend
        ax[i].set_xlabel("Date")
        ax[i].set_title(title, fontsize=14, fontweight="bold")
        ax[i].set_title(title, fontsize=14, fontweight="bold")
        ax[i].spines[["right", "top"]].set_visible(False)
        if rate:
            ax[i].yaxis.set_major_formatter(matplotlib.ticker.StrMethodFormatter("{x:.2f}"))
            ax[i].set_ylabel("%")
        else:
            ax[i].yaxis.set_major_formatter(matplotlib.ticker.StrMethodFormatter("{x:,.0f}"))
            ax[i].set_ylabel("¥bn")
        handles, labels = ax[i].get_legend_handles_labels()
        ax[i].legend(handles, labels, loc="upper left")

    # Save the plot as a PDF (A4 size, portrait)
    plt.savefig(r"BOJ_plot_{}.pdf".format(page), format="pdf", bbox_inches="tight")


def update_progress(progress: float, tag: str):
    """Displays or updates a console progress bar\n
    Accepts a float between 0 and 1. Any int will be converted to a float.\n
    A value under 0 represents a 'halt'.\n
    A value at 1 or bigger represents 100%"""

    bar_length = 40  # Modify to change the length of the progress bar
    status = ""
    if isinstance(progress, int):
        progress = float(progress)
    if not isinstance(progress, float):
        progress = 0
        status = "error: progress var must be float\r\n"
    if progress < 0:
        progress = 0
        status = "Halt...\r\n"
    if progress >= 1:
        progress = 1
        status = "Done...\r\n"
    block = int(round(bar_length * progress))
    text = "\r" + tag + " [{}] {}% {}".format("=" * block + " " * (bar_length - block), int(progress * 100), status)
    sys.stdout.write(text)
    sys.stdout.flush()


def save_to_json(operations: list, file: str) -> bool:
    """Saves a list of operations to a JSON file

    Args:
        operations: the list of daily operations\n
        file: the path of the file to save to

    Returns:
        True: if operation successful\n
        False: if operation failed
    """

    json_ops = {}
    for op in operations:
        op_dic = {}
        date = op.Date.strftime("%Y-%m-%d")
        transactions = []
        for trans in op.Transactions:
            trans_dic = {"Instrument": trans.Instrument,
                         "CompetitiveBids": trans.CompetitiveBids,
                         "SuccessfulBids": trans.SuccessfulBids,
                         "Rate": trans.Rate,
                         "Currency": trans.Currency,
                         "Units": trans.Units}
            transactions.append(trans_dic)
        op_dic["Transactions"] = transactions
        json_ops[date] = op_dic

    json_object = json.dumps(json_ops, indent=4)
    try:
        with open(file, "w") as outfile:
            outfile.write(json_object)
    except IOError:
        return False
    return True


def load_from_json(file: str) -> list:
    """Reads a list of operations from a JSON file

    Args:
        file: the path of the file to read from\n

    Returns:
        a list of operations objects\n
    """

    try:
        with open(file) as json_object:
            json_ops = json.load(json_object)
    except IOError:
        return []

    ops = []
    for key in json_ops:
        op = json_ops[key]
        date = datetime.datetime.strptime(key, "%Y-%m-%d").date()
        new_op = Operation(date)
        for trans in op["Transactions"]:
            new_trans = new_op.AddTransaction(trans["Instrument"], trans["Currency"], trans["Units"])
            new_trans.CompetitiveBids = trans["CompetitiveBids"]
            new_trans.SuccessfulBids = int(trans["SuccessfulBids"])
            new_trans.Rate = float(trans["Rate"])
        ops.append(new_op)
    return ops


if __name__ == "__main__":
    main()
