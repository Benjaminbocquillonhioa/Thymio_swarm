__author__ = 'alessandrozonta'

import sys
import math
import traceback
import threading
import numpy as np
import io

import cv2
import picamera

# Recognize color using the camera
class cameraVision(threading.Thread):
    def __init__(self, camera, simulationLogger):
        threading.Thread.__init__(self)
        self.CAMERA_WIDTH = 320
        self.CAMERA_HEIGHT = 240
        self.scale_down = 1
        self.presence = [0, 0, 0, 0]
        self.presenceGoal = [0, 0, 0, 0]
        self.camera = camera
        self.__isCameraAlive = threading.Condition()
        self.__isStopped = threading.Event()
        self.__simLogger = simulationLogger
        self.__imageAreaThreshold = 1000

    def stop(self):
        self.__isStopped.set()
        with self.__isCameraAlive:
            self.__isCameraAlive.notify()

    def __stopped(self):
        return self.__isStopped.isSet()

    def readPuckPresence(self):
        return self.presence

    def readGoalPresence(self):
        return self.presenceGoal

    #  return contours with largest area in the image
    def retMaxArea(self, contours):
        max_area = 0
        largest_contour = None
        for idx, contour in enumerate(contours):
            area = cv2.contourArea(contour)
            if area > max_area:
                max_area = area
                largest_contour = contour
        return largest_contour

    # return area of the largest contour
    def retLargestContour(self, contour, image2, name):
        if not contour is None:
            moment = cv2.moments(contour)
            # m00 is the area
            if moment["m00"] > self.__imageAreaThreshold / self.scale_down:
                # rect_bl = cv2.minAreaRect(contour)
                # rect_bl = ((rect_bl[0][0] * self.scale_down, rect_bl[0][1] * self.scale_down),
                #            (rect_bl[1][0] * self.scale_down, rect_bl[1][1] * self.scale_down), rect_bl[2])
                # box_bl = cv2.cv.BoxPoints(rect_bl)
                # box_bl = np.int0(box_bl)
                # cv2.drawContours(image2, [box_bl], 0, (255, 255, 0), 2)
                # cv2.imshow(name, image2)
                return moment["m00"]
        return 0

    # return sum of the area of all the contours in the image
    def retAllContours(self, contours):
        presence = 0
        for idx, contour in enumerate(contours):
            moment = cv2.moments(contour)

            # m00 is the area
            if moment["m00"] > self.__imageAreaThreshold / self.scale_down:
                presence += moment["m00"]
        return presence

    def retContours(self, lower_color, upper_color, image_total, selector):
        presence = [0, 0, 0, 0]
        binary = cv2.inRange(image_total["bottom"], lower_color, upper_color)
        binary_left = cv2.inRange(image_total["left"], lower_color, upper_color)
        binary_central = cv2.inRange(image_total["central"], lower_color, upper_color)
        binary_right = cv2.inRange(image_total["right"], lower_color, upper_color)

        dilation = np.ones((15, 15), "uint8")

        color_binary = cv2.dilate(binary, dilation)
        color_binary_left = cv2.dilate(binary_left, dilation)
        color_binary_central = cv2.dilate(binary_central, dilation)
        color_binary_right = cv2.dilate(binary_right, dilation)

        binary_total = [color_binary_left, color_binary_central, color_binary_right, color_binary]

        for i in range(len(binary_total)):
            binary_total[i] = cv2.GaussianBlur(binary_total[i], (5, 5), 0)

        contours_total = []
        for el in binary_total:
            # This works only with OpenCV 2.4. OpenCV 3.0 needs three things :(
            (major_ver, minor_ver, subminor_ver) = cv2.__version__.split('.')
            if int(major_ver) < 3:  # OpenCV 2.4
                contours, hierarchy = cv2.findContours(el, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
            else:  # OpenCV 3.0
                img, contours, hierarchy = cv2.findContours(el, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
            contours_total.append(contours)

        # selector == 0 check only largest area
        if selector == 0:
            largest_contour_total = []
            # Checking the largest area
            for el in contours_total:
                largest_contour_total.append(self.retMaxArea(el))


            # returning the value of the largest contour
            for i in range(len(largest_contour_total)):
                name = image_total.keys()[i]
                presence[i] = self.retLargestContour(largest_contour_total[i], image_total[name], name)

        else:
            # selector == 1 check all the area
            for i in range(len(contours_total)):
                presence[i] = self.retAllContours(contours_total[i])

        return presence

    def run(self):
        try:
            with picamera.PiCamera() as camera:
                camera.resolution = (self.CAMERA_WIDTH, self.CAMERA_HEIGHT)
                camera.framerate = 30

                # capture into stream
                stream = io.BytesIO()
                for foo in camera.capture_continuous(stream, 'jpeg'):
                    data = np.fromstring(stream.getvalue(), dtype=np.uint8)
                    # "Decode" the image from the array, preserving colour
                    image = cv2.imdecode(data, 1)

                    # Convert BGR to HSV
                    image = cv2.GaussianBlur(image, (5, 5), 0)
                    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
                    # Resize image
                    hsv = cv2.resize(hsv, (len(image[0]) / self.scale_down, len(image) / self.scale_down))

                    # Calculate value to divide the image into three/four different part
                    valueDivision = math.floor((self.CAMERA_WIDTH / 3) / self.scale_down)
                    valueDivisionVertical = math.floor((self.CAMERA_HEIGHT / 4) / self.scale_down)

                    # Divide image in three pieces
                    sub_image_left = hsv[0:valueDivisionVertical * 3, 0:0 + valueDivision]
                    sub_image_central = hsv[0:valueDivisionVertical * 3,
                                        valueDivision:valueDivision + valueDivision]
                    sub_image_right = hsv[0:valueDivisionVertical * 3,
                                      valueDivision + valueDivision: (self.CAMERA_WIDTH / self.scale_down)]
                    sub_image_bottom = hsv[valueDivisionVertical * 3:]

                    image_total = {"left": sub_image_left, "central": sub_image_central,
                                   "right": sub_image_right, "bottom": sub_image_bottom}

                    # define range of blue color in HSV
                    lower_blue = np.array([80, 60, 50])
                    upper_blue = np.array([120, 255, 255])

                    # define range of red color in HSV
                    # My value
                    red_lower = np.array([125, 130, 80])
                    red_upper = np.array([180, 255, 255])

                    # define range of green color in HSV
                    green_lower = np.array([30, 75, 75])
                    green_upper = np.array([60, 255, 255])

                    # define range of white color in HSV
                    test = 110
                    lower_white = np.array([0, 0, 255 - test])
                    upper_white = np.array([360, test, 255])

                    # define range of black color in HSV
                    black_lower = np.array([0, 0, 0])
                    black_upper = np.array([180, 255, 30])

                    self.presence = self.retContours(red_lower, red_upper, image_total, 0)

                    # black color changed into blu color (thymio doesn't have blu part. Only goal is blu)
                    self.presenceGoal = self.retContours(lower_blue, upper_blue, image_total, 1)

                    # print("presenceRed {}".format(self.presence))
                    # print("presenceBlack {}".format(self.presenceGoal))
                    # print("presenceBlack {}".format(self.presenceGoal))

                    if self.camera:
                        cv2.imshow("ColourTrackerWindow", image)
                    # cv2.imshow("sub_image_left", sub_image_left)
                    # cv2.imshow("sub_image_central", sub_image_central)
                    # cv2.imshow("sub_image_right", sub_image_right)
                    # cv2.imshow("sub_image_bottom", sub_image_bottom)

                    stream.truncate()
                    stream.seek(0)

                    # stop thread
                    if self.__stopped():
                        self.__simLogger.debug("Stopping camera thread")
                        break
            cv2.destroyAllWindows()
        except Exception as e:
            self.__simLogger.critical("Camera exception: " + str(e) + str(
                sys.exc_info()[0]) + ' - ' + traceback.format_exc())