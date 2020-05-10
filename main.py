#!/usr/bin/env python3
# -*- coding: utf-8 -*-

###############################################################################
# built-ins
from collections import defaultdict
from itertools import groupby, product, chain, combinations
from re import compile as re_compiler
from sys import exit, argv
from time import strptime
from datetime import datetime
from enum import Enum, auto
import logging
import json
import asyncio

###############################################################################
# imports
import aiohttp
from tabulate import tabulate
from PySide2.QtGui import QIcon
from PySide2.QtWidgets import (QApplication, QComboBox, QDesktopWidget,
                               QDialogButtonBox, QFileDialog, QHBoxLayout, QGridLayout,
                               QLabel, QPushButton, QVBoxLayout, QWidget, QDialog, QFrame)
from PySide2.QtCore import Qt

###############################################################################
# Simple logging suite
logging.basicConfig(
    filename="main.log",
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%d/%m/%Y %H:%M:%S")
log = logging.getLogger(__name__)

###############################################################################
# Global vars

# Regex expression to manage course sections
SECTION_REGEX = re_compiler(r"(?:\d+)([a-zA-Z]+)")

# Enumeration of days
DAY_TABLE = {"M": 0, "T": 1, "W": 2, "R": 3, "F": 4, "S": 5, "*": 6}
API = "https://registrar.nu.edu.kz/my-registrar/public-course-catalog/json"
HEADERS = {"Host": "registrar.nu.edu.kz",
           "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4044.129 Safari/537.36",
           "Referer": "https://registrar.nu.edu.kz/course-catalog",
           "Content-Type": "application/x-www-form-urlencoded",
           "X-Requested-With": "XMLHttpRequest",
           "Connection": "keep-alive"}

##############################################################################
# Fetch config
SEMESTER_ID = "442"                 # Spring 2020
SCHOOL_IDS = ["13", "12"]           # SSH and SEDS
LEVEL_IDS = "1"                     # Undergraduate

#############################################################################


class Request(Enum):
    COURSE = auto()
    SCHEDULE = auto()


async def fetch(session: aiohttp.ClientSession, request_type: Request, page=1, courseid=""):
    if request_type == Request.COURSE:
        data = {"method": "getSearchData",
                "searchParams[formSimple]": "false",
                "searchParams[limit]": "100",
                "searchParams[page]": f"{page}",
                "searchParams[start]": "0",
                "searchParams[quickSearch]": "",
                "searchParams[sortField]": "-1",
                "searchParams[sortDescending]": "-1",
                "searchParams[semester]": SEMESTER_ID,
                "searchParams[schools][]": SCHOOL_IDS,
                "searchParams[departments]": "",
                "searchParams[levels][]": LEVEL_IDS,
                "searchParams[subjects]": "",
                "searchParams[instructors]": "",
                "searchParams[breadths]": "",
                "searchParams[abbrNum]": "",
                "searchParams[credit]": ""
                }
    else:
        data = {"method": "getSchedule",
                "courseId": courseid,
                "termId": SEMESTER_ID}
    async with session.post(API, headers=HEADERS, data=data) as response:
        parsed_response = await response.json(content_type="text/html")
        return parsed_response if request_type == Request.COURSE else (courseid, parsed_response)


async def fetch_worker():
    async with aiohttp.ClientSession() as session:
        # the first courses page
        tasks, courses = [], await fetch(session, Request.COURSE)

        # working on the courses
        max_range = 3 + int(courses["total"]) // 100
        for i in range(2, max_range):
            tasks.append(fetch(session, Request.COURSE, i))
        other_course_pages = await asyncio.gather(*tasks)
        for i in other_course_pages:
            courses["data"] += i["data"]

        # working on the schedules
        tasks = []
        for i in courses["data"]:
            tasks.append(
                fetch(session, Request.SCHEDULE, courseid=i["COURSEID"]))

        schedules = await asyncio.gather(*tasks)
        for courseid, i in schedules:
            for j in courses["data"]:
                if j["COURSEID"] == courseid:
                    j["SCHEDULE"] = i
                    break

        return courses

###############################################################################


class Course():

    """Models courses as a class"""

    def __init__(self, abbr, st, title, credit, days, timing, teacher, room):
        self.abbr = str(abbr)
        self.st = str(st)
        self.title = str(title)
        self.credit = str(credit)
        self.days = str(days)
        self.timing = str(timing)
        self.teacher = str(teacher)
        self.room = str(room)

        if self.timing != "*":
            a, b = self.timing.split("-")
            self.start, self.end = strptime(
                a, "%I:%M %p"), strptime(b, "%I:%M %p")
        else:
            self.start, self.end = str(), str()
        self.dayslist = [DAY_TABLE.get(i) for i in DAY_TABLE if i in self.days]

    def __repr__(self):
        return f"{self.abbr} | {self.st} | {self.title} | {self.credit} | {self.days} | {self.timing} | {self.teacher} | {self.room}"

    def __and__(self, other):
        """ Intersection check """

        if 6 in set(self.dayslist) or 6 in set(other.dayslist):
            return False

        if not set.intersection(set(self.dayslist), set(other.dayslist)):
            return False
        else:
            return self.start <= other.end and self.end >= other.start

###############################################################################


class UI(QWidget):

    """Simple Qt UI"""

    coursesconnector, finallist = list(), list()

    def __init__(self, parent=None):
        """ Initializing """

        super(UI, self).__init__(parent)
        self.initui()

    def center(self):
        """ Centering magic """

        qr = self.frameGeometry()
        cp = QDesktopWidget().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

    def on_about_clicked(self):
        """ About pop-up """

        d = QDialog()
        l1 = QLabel(
            "nu-schedule\n\nA course schedule generator for the Nazarbayev University\nHomepage: https://github.com/ac130kz/nu-schedule\nApache 2.0 License\n\n© Mikhail Krassavin, 2020")
        b1 = QPushButton("Ok", d)
        vbox = QVBoxLayout()
        vbox.addWidget(l1)
        hbox = QHBoxLayout()
        hbox.addStretch()
        hbox.addWidget(b1)
        hbox.addStretch()
        vbox.addItem(hbox)
        d.setWindowIcon(QIcon("res/logo.ico"))
        d.setWindowTitle("About")
        d.setLayout(vbox)
        b1.clicked.connect(d.accept)
        d.exec_()

    def on_help_clicked(self):
        """ Help pop-up """

        d = QDialog()
        l1 = QLabel("1. Press |Load| to download the latest data for the semester.\n\n3. With |Edit| button access the selection menu,\nadded courses will appear on the Main window.\n\n4. Use |Generate| button to generate and\n save your schedule as result<unixtimestamp>.txt")
        b1 = QPushButton("Ok", d)
        vbox = QVBoxLayout()
        vbox.addWidget(l1)
        hbox = QHBoxLayout()
        hbox.addStretch()
        hbox.addWidget(b1)
        hbox.addStretch()
        vbox.addItem(hbox)
        d.setWindowIcon(QIcon("res/logo.ico"))
        d.setWindowTitle("Help")
        d.setLayout(vbox)
        b1.clicked.connect(d.accept)
        d.exec_()

    def on_edit_clicked(self):
        """ Editing course selection """

        if self.coursesconnector:
            d = QDialog()
            add = QPushButton("Add", d)
            delete = QPushButton("Delete", d)
            cmb1 = QComboBox()
            cmb1.addItems(sorted([t[0] for t in self.coursesconnector]))
            hbox = QHBoxLayout()
            hbox.addWidget(cmb1)
            hbox.addStretch()
            hbox.addWidget(add)
            hbox.addWidget(delete)
            hbox.addStretch()
            d.setWindowIcon(QIcon("res/logo.ico"))
            d.setWindowTitle("Adding courses")
            d.setLayout(hbox)
            add.clicked.connect(
                lambda: self.on_add_clicked(cmb1.currentText()))
            delete.clicked.connect(
                lambda: self.on_delete_clicked(cmb1.currentText()))
            d.exec_()

    def get_finallistsize(self):
        """ Updating the info on the selection list """

        if not self.finallist:
            data = "empty"
        else:
            data = str(set(y[0].abbr for y in self.finallist))
        self.label.setText(f"Your selection is: \n{data}")

    def fail_dialog(self):
        """ Is triggered if schedules cannot be created """

        d = QDialog()
        b1 = QPushButton("Ok", d)
        lbl1 = QLabel("Cannot create a schedule with these subjects")
        vbox = QVBoxLayout()
        vbox.addWidget(lbl1)
        vbox.addStretch()
        vbox.addWidget(b1)
        vbox.addStretch()
        d.setWindowTitle("Failed")
        d.setLayout(vbox)
        b1.clicked.connect(d.accept)
        d.setWindowIcon(QIcon("res/logo.ico"))
        self.get_finallistsize()
        d.exec_()

    def success_dialog(self, desc):
        """ Is triggered if schedules were created """

        d = QDialog()
        b1 = QPushButton("Ok", d)
        lbl1 = QLabel(f"Results successfully saved as result{desc}.txt")
        vbox = QVBoxLayout()
        vbox.addWidget(lbl1)
        vbox.addStretch()
        vbox.addWidget(b1)
        vbox.addStretch()
        d.setWindowTitle("Success")
        d.setLayout(vbox)
        b1.clicked.connect(d.accept)
        d.setWindowIcon(QIcon("res/logo.ico"))
        self.get_finallistsize()
        d.exec_()

    def empty_dialog(self):
        """ Is triggered if course selection is empty """

        d = QDialog()
        b1 = QPushButton("Ok", d)
        lbl1 = QLabel("Your selection of courses is empty")
        vbox = QVBoxLayout()
        vbox.addWidget(lbl1)
        vbox.addStretch()
        vbox.addWidget(b1)
        vbox.addStretch()
        d.setWindowTitle("Selection empty")
        d.setLayout(vbox)
        b1.clicked.connect(d.accept)
        d.setWindowIcon(QIcon("res/logo.ico"))
        d.exec_()

    def on_add_clicked(self, text):
        """ Course addition functionality """

        if not any(text == x[0].abbr for x in self.finallist):
            for k, v in self.coursesconnector:
                if k == text:
                    for i in v:
                        self.finallist.append(i)
            self.get_finallistsize()

    def on_delete_clicked(self, text):
        """ Course deletion functionality """

        self.finallist = [x for x in self.finallist if text != x[0].abbr]
        self.get_finallistsize()

    def on_load_clicked(self):
        """ Data loading procedure """
        self.label.setText(
            "Loading... Application can be unresponsive for 20 seconds")
        QApplication.processEvents()

        try:
            loop = asyncio.get_event_loop()
            data = loop.run_until_complete(fetch_worker())
            if data:
                courses = list()
                for i in data["data"]:
                    for j in i["SCHEDULE"]:
                        courses.append(Course(
                            i["ABBR"], j["ST"], i["TITLE"], i["CRECTS"],
                            j["DAYS"], j["TIMES"], j["FACULTY"], j["ROOM"]))

                self.label.setText("Successfully loaded")
                courses = self.groupabbr(courses)
                self.coursesconnector = courses
            else:
                self.label.setText("Empty data")
        except Exception as e:
            log.exception(e)

    def on_gen_clicked(self):
        """ Results output """

        if self.finallist:
            self.label.setText("Generating schedule...")
            QApplication.processEvents()

            log.info(f"Generating schedule for {self.finallist}")
            outlist = [p for p in product(
                *self.finallist) if not any(one & two for one, two in combinations(p, 2))]
            temp = 1
            d = str(datetime.utcnow().timestamp())

            if outlist:
                with open("result" + d + ".txt", "w") as file:
                    for k in outlist:
                        file.write(f"Schedule #{temp}\n")
                        headers = ["Abbreviation", "Section", "Title",
                                   "ECTS Credits", "Days", "Time", "Teacher", "Room"]

                        file.write(tabulate([[elem.__dict__["abbr"], elem.__dict__["st"], elem.__dict__["title"], elem.__dict__["credit"], elem.__dict__["days"],
                                              elem.__dict__["timing"], elem.__dict__["teacher"], elem.__dict__["room"]] for elem in list(k)], headers, tablefmt="grid"))
                        file.write("\n\n")
                        temp = temp + 1
                self.success_dialog(d)
                log.info(f"Results are {outlist}")
                log.info(f"Results successfully saved as result{d}.txt")
            else:
                self.fail_dialog()
                log.info("Cannot create a schedule with these courses")
        else:
            self.empty_dialog()
            log.info(
                f"List to generate schedule is assumed to be zero and it is currently {self.finallist}")

    def groupabbr(self, inlist):
        """ Forms a list of course lists based on the course abbreviation and section (s/t) """

        result = defaultdict(lambda: defaultdict(list))

        for obj in inlist:
            result[obj.abbr][SECTION_REGEX.search(obj.st).group(1)].append(obj)

        inlist = [(list(r.values())[0][0].abbr, list(r.values()))
                  for r in result.values()]
        log.info("Courses were sorted")
        return inlist

    def initui(self):
        """ Main window UI """

        # Defining labels
        self.label = QLabel(self)
        self.label.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        if not self.finallist:
            self.label.setText("Data was not loaded")

        # Defining buttons
        load_button = QPushButton("Load")
        edit_button = QPushButton("Edit needed courses")
        help_button = QPushButton("Help")
        about_button = QPushButton("About")
        gen_button = QPushButton("Generate!")
        gen_button.setStyleSheet(
            "QPushButton {background-color: #c7f439; color: red; font-size: 50px;}")

        # Dealing with the interface of the app
        grid = QGridLayout()
        grid.addWidget(load_button)
        grid.addWidget(edit_button)
        grid.addWidget(help_button)
        grid.addWidget(about_button)
        grid.addWidget(self.label)
        grid.addWidget(gen_button)
        self.setLayout(grid)

        # Slot calls
        help_button.clicked.connect(self.on_help_clicked)
        edit_button.clicked.connect(self.on_edit_clicked)
        about_button.clicked.connect(self.on_about_clicked)
        load_button.clicked.connect(self.on_load_clicked)
        gen_button.clicked.connect(self.on_gen_clicked)

        # Setting window properties
        self.setGeometry(600, 300, 500, 270)
        self.center()
        self.setWindowTitle("nu-schedule")
        self.setWindowIcon(QIcon("res/logo.ico"))
        self.show()
        log.info("Main window loaded")


if __name__ == "__main__":
    log.info("Starting the app")
    app = QApplication(argv)
    widget = UI()
    exit(app.exec_())
