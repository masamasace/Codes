
"""
CONCERNS
01 スレッドは殺す必要がある？
02 スレッド用クラスを作った方がよい？

TODO
01 初期設定をxmlから読み込み
02 クローズ時に設定を保存
03 queueの読み込み時と書き込み時にThreadsafeな書き方に変更

"""

from src.hx711 import HX711
import RPi.GPIO as GPIO
import board
import busio
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn
import time
import PySimpleGUI as sg
from collections import deque
import queue
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import csv
import multiprocessing as mp

# magic code for plt
# plt.rcParams["font.family"] = "Times"
# plt.rcParams["mathtext.fontset"] = "stix" 

class window():
    def __init__(self):
        
        # variables for adc
        self.sampling_rate_adc = 2.
        self.time_interval_adc = 1 / self.sampling_rate_adc
        self.max_num_queue_read = 100

        # variables for calibration
        self.gain = [1569.15/110600, 19.5/12500]
        self.intercept = [0., 0.]
        
        # variables for figure
        self.graph_max = [100., 100.]
        self.graph_min = [-100., -100.]
        self.max_num_queue_graph = 100
        self.sampling_rate_graph = 5.
        self.time_interval_graph = 1 / self.sampling_rate_graph

        # variables for condition of saving and monitoring
        self.save_dir = "(file path)"
        self.is_saving = False
        self.is_monitoring = True
        self.is_already_read = False

        # variables
        self.y0_read = mp.Queue(maxsize=self.max_num_queue_read)
        self.y1_read = mp.Queue(maxsize=self.max_num_queue_read)
        self.x_graph = mp.Queue(maxsize=self.max_num_queue_graph)
        self.y0_graph = mp.Queue(maxsize=self.max_num_queue_graph)
        self.y1_graph = mp.Queue(maxsize=self.max_num_queue_graph)

        self._initialize_ADC()
        self._intiialize_window()
        self._update_window()


    # ------- initialize ADC --------
    def _initialize_ADC(self):
        self._initialize_hx711()
        self._initialize_ads1115()


    # ------- initialize HX711 --------
    def _initialize_hx711(self):
        print("initilaizing start (hx711)")
        self.hx = HX711(5, 6)
        self.hx.set_reading_format("MSB", "MSB")
        self.hx.set_reference_unit(1)
        self.hx.reset()
        self.hx.tare()
        print("initilaizing end   (hx711)")
    
    # ------- initialize ADS1115 --------
    def _initialize_ads1115(self):
        print("initilaizing start (ads1115)")
        i2c = busio.I2C(board.SCL, board.SDA)
        ads = ADS.ADS1115(i2c)
        ads.gain = 4
        ads.data_rate = 860
        self.chan = AnalogIn(ads, ADS.P0, ADS.P1)
        print("initilaizing end   (ads1115)")

    # ------- start reading --------
    def _update_window(self):

        # ------- initialize hx711 module --------
        process_hx711 = mp.Process(target=self._read_hx711, args=(self.y0_read, ))
        process_hx711.start()
        process_ads1115 = mp.Process(target=self._read_ads1115, args=(self.y1_read, ))
        process_ads1115.start()
        process_update_graph_value = mp.Process(target=self._update_graph_value, args=(self.x_graph, self.y0_graph, self.y1_graph))
        process_update_graph_value.start()

        self.start_time = time.time()

        while True:

            prev_y0 = 0.0
            prev_y1 = 0.0

            array_y0_read = self._dump_queue(self.y0_read)
            array_y1_read = self._dump_queue(self.y1_read)

            
            if len(array_y0_read) != 0:
                current_y0 = array_y0_read.mean()
            else:
                current_y0 = prev_y0
            
            if len(array_y1_read) != 0:
                current_y1 = array_y1_read.mean()
            else:
                current_y1 = prev_y1

            current_time_adc = time.time() - self.start_time

            self.x_graph.put(current_time_adc)
            self.y0_graph.put(current_y0)
            self.y1_graph.put(current_y1)

            time.sleep(self.time_interval_adc)
        
        process_update_graph_value.terminate()
        process_hx711.terminate()
        process_ads1115.terminate()
        GPIO.cleanup()
        self.window.close()


    def _dump_queue(self, y):
        result = []

        for i in range(self.max_num_queue_read):
            # print(queue.get())
            try:
                temp = y.get_nowait()
            except queue.Empty:
                break
            else:
                result.append(temp)

        return np.array(result)

    
    # ------- read the value of hx711 module --------
    def _read_hx711(self, y0_read):

        print("start reading hx711")
        current_y0_read = 0.0

        # ------- read the value --------
        while True:
            current_y0_read = self.hx.get_weight(5)
            y0_read.put(current_y0_read)
            

    # ------- read the value of ads1115 module --------
    def _read_ads1115(self, y1_read):

        # ------- read the value --------
        print("start reading ads1115")
        current_y1_read = 0.0

        while True:
            current_y1_read = self.chan.value
            y1_read.put(current_y1_read)


    # ------- initialize window --------
    def _intiialize_window(self):
        print("initializing start (window)")
        layout_gain = sg.Frame("Gain", [[sg.Text("CH No.", size=(7, 1)), sg.Text("Param A (Slope)", size=(14, 1)), sg.Text("Param B (Intercept)", size=(16, 1))],
                                        [sg.Text("CH0", size=(7, 1)), sg.InputText(self.gain[0], enable_events=True, key='gain_change_CH0', size=(16, 1)), sg.InputText(self.intercept[0], key='intercept_change_CH0', enable_events=True, size=(16, 1))],
                                        [sg.Text("CH1", size=(7, 1)), sg.InputText(self.gain[1], enable_events=True, key='gain_change_CH1', size=(16, 1)), sg.InputText(self.intercept[0], key='intercept_change_CH1', enable_events=True, size=(16, 1))]])
        layout_ADC =  sg.Frame("ADC", [[sg.Text("Sampling Rate", size=(12, 1)), sg.InputText(self.sampling_rate_adc, enable_events=True, key='sampling_rate_adc_change', size=(6, 1))],
                                       [sg.Text("Tare Vol", size=(12, 2)), sg.Button("CH0", key='tare_CH0', disabled=True, size=(3, 2)), sg.Button("CH1", key='tare_CH1', disabled=True, size=(3, 2))]])
        layout_graph_control = sg.Frame("Graph Control", [[sg.Text("CH No.", size=(7, 1)), sg.Text("Max", size=(6, 1)), sg.Text("Min", size=(6, 1)), sg.Text("Displayed Points", size=(16, 1))],
                                                          [sg.Text("CH0", size=(7, 1)), sg.InputText(self.graph_max[0], enable_events=True, key='max_change_CH0', size=(7, 1)), sg.InputText(self.graph_min[0], enable_events=True, key='min_change_CH0', size=(7, 1)), sg.InputText(self.max_num_queue_graph, enable_events=True, key='num_disp_points_change_CH0', size=(16, 1))],
                                                          [sg.Text("CH1", size=(7, 1)), sg.InputText(self.graph_max[1], enable_events=True, key='max_change_CH1', size=(7, 1)), sg.InputText(self.graph_min[1], enable_events=True, key='min_change_CH1', size=(7, 1)), sg.InputText("-", readonly=True, key='num_disp_points_change_CH1', size=(16, 1))]])
        layout_record_monitor = sg.Frame("Record & Monitor", [[sg.FileSaveAs(button_text="Start Saving", key='start_saving', target="save_file_path", default_extension=".csv", size=(10, 1)), sg.Button("Stop Saving", disabled=True, key='stop_saving', size=(10, 1))],
                                                              [sg.Button("Start\nMonitoring", disabled=True, key='start_monitoring', size=(10, 2)), sg.Button("Stop\nMonitoring", key='stop_monitoring', size=(10, 2))]])
        layout_save_file_path = [sg.Text("Save File Path"), sg.InputText(default_text="(file path)", enable_events=True, key="save_file_path", size=(64, 1), readonly=True)]
        layout_graph = sg.Canvas(key='-CANVAS-')
        layout_all = [[layout_gain, layout_ADC], [layout_graph_control, layout_record_monitor], [layout_save_file_path], [layout_graph]]

        
        # Create the Window
        self.window = sg.Window('DigitShowBasic Mini', layout_all, finalize=True)

        
        # initialize graph
        fig = plt.figure(figsize=(5.5, 5))

        # plt.subplots_adjust(hspace=0.2, right=0.95, top=0.95)
        self.ax1 = fig.add_subplot(211)
        self.ax2 = fig.add_subplot(212)
        self.line1,  = self.ax1.plot(0, 0)
        self.line2,  = self.ax2.plot(0, 0)
        self.ax1.grid(linestyle=":", linewidth=0.5, color="k")
        self.ax2.grid(linestyle=":", linewidth=0.5, color="k")
        self.ax2.set_xlabel("Time (sec)")
        self.ax1.set_ylabel("Load Cell (g)")
        self.ax2.set_ylabel("Pore Water \n Pressure Gauge (kPa)")

        self.fig_agg = self._draw_figure(self.window['-CANVAS-'].TKCanvas, fig)
        print("initializing end (window)")
        

    # ------- update window --------
    def _update_graph_value(self, queue_x_graph, queue_y0_graph, queue_y1_graph):
        
        temp_queue_x_graph = deque(maxlen=self.max_num_queue_graph)
        temp_queue_y0_graph = deque(maxlen=self.max_num_queue_graph)
        temp_queue_y1_graph = deque(maxlen=self.max_num_queue_graph)

        prev_x_last_value = 0.

        while True:

            current_time_window = time.time()

            event, values = self.window.read(timeout=0.001)
            
            if event == sg.WIN_CLOSED or event == 'Cancel':
                break
            
            if event != "__TIMEOUT":
                self._update_values(event, values)

            for i in range(self.max_num_queue_graph):
                try:
                    temp = queue_x_graph.get_nowait()
                except queue.Empty:
                    break
                else:
                    temp_queue_x_graph.append(temp)
                    temp_queue_y0_graph.append(queue_y0_graph.get()) 
                    temp_queue_y1_graph.append(queue_y1_graph.get())
    

            array_x_graph = np.array(temp_queue_x_graph)
            array_y0_graph = np.array(temp_queue_y0_graph)
            array_y1_graph = np.array(temp_queue_y1_graph)

            if self.is_saving and prev_x_last_value != array_x_graph[-1]:
                prev_x_last_value = array_x_graph[-1]
                with open(self.save_dir, "a", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow([array_x_graph[-1], array_y0_graph[-1], array_y1_graph[-1], 
                                     array_y0_graph[-1]*self.gain[0] + self.intercept[0], 
                                     array_y1_graph[-1]*self.gain[1] + self.intercept[1]])

            if self.is_monitoring:
                # plot ax1
                self.line1.set_data(array_x_graph, array_y0_graph*self.gain[0] + self.intercept[0])
                self.line2.set_data(array_x_graph, array_y1_graph*self.gain[1] + self.intercept[1])

                # grpah properties
                self.ax1.set_ylim([self.graph_min[0], self.graph_max[0]])
                self.ax2.set_ylim([self.graph_min[1], self.graph_max[1]])
                
                if len(array_x_graph) != 0:
                    x_lim = [array_x_graph[0], array_x_graph[-1]]
                else:
                    x_lim = [0, 1]

                self.ax1.set_xlim(x_lim)
                self.ax2.set_xlim(x_lim)

                # update changes
                self.fig_agg.draw()
            
            sleep_time = time.time() - current_time_window - self.time_interval_graph
        
            if sleep_time < 0:
                time.sleep(-sleep_time)
        
        print("break")
        return 0
            

    
    def _update_values(self, event, values):

        if "gain" in event:
            try:
                float(values[event])
            except ValueError as e:
                print(e)
            else:
                self.gain[int(event[-1])] = float(values[event])

        elif "intercept" in event:
            try:
                float(values[event])
            except ValueError as e:
                print(e)
            else:
                self.intercept[int(event[-1])] = float(values[event])

        elif "sampling_rate_adc" in event:
            try:
                float(values[event])
            except ValueError as e:
                print(e)
            else:
                self.sampling_rate_adc = float(values[event])
                try:
                    1 / self.sampling_rate_adc
                except ZeroDivisionError as e:
                    print(e)
                else:
                    self.time_interval_adc = 1 / self.sampling_rate_adc

        elif "max" in event:
            try:
                float(values[event])
            except ValueError as e:
                print(e)
            else:
                self.graph_max[int(event[-1])] = float(values[event])

        elif "min" in event:
            try:
                float(values[event])
            except ValueError as e:
                print(e)
            else:
                self.graph_min[int(event[-1])] = float(values[event])

        elif "num_disp_points" in event:
            try:
                int(values[event])
            except ValueError as e:
                print(e)
            else:
                self.max_num_queue_graph[int(event[-1])] = int(values[event])
                self.x_graph = deque(maxlen=self.max_num_queue_graph)
                self.y0_graph = deque(maxlen=self.max_num_queue_graph)
                self.y1_graph = deque(maxlen=self.max_num_queue_graph)
        elif "tare" in event:
            pass
        
        elif "save_file_path" in event:
            if self.save_dir != values[event]:
                self.save_dir = values[event]
                self.window.FindElement("start_saving").Update(disabled=True)
                self.window.FindElement("stop_saving").Update(disabled=False)
                self.is_saving = True
                with open(self.save_dir, "w", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(["Time(s)", "CH1_Vol(V)", "CH2_Vol(V)", "CH1_Weight(N)", "CH2_Hydraulic_Pressure(kPa)"])

        elif "stop_saving" in event:
            self.is_saving = False
            self.window.FindElement("start_saving").Update(disabled=False)
            self.window.FindElement("stop_saving").Update(disabled=True)

        elif "start_monitoring" in event:
            self.is_monitoring = True
            self.window.FindElement("start_monitoring").Update(disabled=True)
            self.window.FindElement("stop_monitoring").Update(disabled=False)

        elif "stop_monitoring" in event:
            self.is_monitoring = False
            self.window.FindElement("stop_monitoring").Update(disabled=True)
            self.window.FindElement("start_monitoring").Update(disabled=False)


    def _draw_figure(self, canvas, figure):
        figure_canvas_agg = FigureCanvasTkAgg(figure, canvas)
        figure_canvas_agg.draw()
        figure_canvas_agg.get_tk_widget().pack(side='top', fill='both', expand=1)
        return figure_canvas_agg

    
def main():
   window() 
