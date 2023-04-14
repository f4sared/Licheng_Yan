
# from IPython.core.debugger import set_trace

import copy
import numpy as np
import random
import json
from collections import defaultdict
from alns import State

class Parser(object):
    
    def __init__(self, json_file):
        '''initialize the parser, saves the data from the file into the following instance variables:
        - 
        Args:
            json_file::str
                the path to the xml file
        '''
        self.json_file = json_file
        with open(json_file, 'r') as f:
            self.data = json.load(f)
        self.name = self.data['name']
        self.Alpha = self.data['Alpha']
        self.T = self.data['T']
        self.BMAX = self.data['BMax']
        self.WMAX = self.data['WMax']
        self.RMIN = self.data['RMin']

        self.workers = [Worker(worker_data, self.T, self.BMAX, self.WMAX, self.RMIN) for worker_data in self.data['Workers']]
        self.tasks = [Task(task_data) for task_data in self.data['Tasks']]
        
        print('workers:',len(self.workers))
        print('tasks:',len(self.tasks))
        
class Task(object):
    
    def __init__(self, data):
        self.id = data['t_id']
        self.skill = data['skill']
        self.day = data['day']
        self.hour = data['hour']

class Worker(object):
    
    def __init__(self, data, T, bmax, wmax, rmin):
        '''Initialize the worker
        Attributes:
            id::int
                id of the worker
            skills::[skill]
                a list of skills of the worker
            available::{k: v}
                key is the day, value is the list of two elements, 
                the first element in the value is the first available hour for that day,
                the second element in the value is the last available hour for that day, inclusively
            bmax::int
                maximum length constraint
            wmax::int
                maximum working hours
            rmin::int
                minimum rest time
            rate::int
                hourly rate
            tasks_assigned::[task]
                a list of task objects
            blocks::{k: v}
                key is the day where a block is assigned to this worker
                value is the list of two elements
                the first element is the hour of the start of the block
                the second element is the hour of the end of the block, inclusively
                if a worker is not assigned any tasks for the day, the key is removed from the blocks dictionary:
                        Eg. del self.blocks[D]

            total_hours::int
                total working hours for the worker
            
        '''
        self.id = data['w_id']
        self.skills = data['skills']
        self.T = T
        self.available = {int(k):v for k,v in data['available'].items()}
        # the constant number for f2 in the objective function
        self.bmin = 4
        self.bmax = bmax
        self.wmax = wmax
        self.rmin = rmin
        
        self.rate = data['rate']
        
        self.tasks_assigned = []
        self.blocks = {}
        self.total_hours = 0
        
    def can_assign(self, task):
        
        # check skill set & day required is available >> worker is eligible for task 
        if task.skill in self.skills and task.day in self.available.keys():
#             print('worker is eligible')

        ## check available time slots >> task is within worker's availability 
            if task.hour >= self.available[task.day][0] and task.hour <= self.available[task.day][1]:
#                 print('task within worker hours')

        ### for cases where nothing was assigned to this worker for that day 
                if len([x.hour for x in self.tasks_assigned if x.day == task.day]) == 0: 
                    ## check if this is within wmax 
                    if self.total_hours + 1 > self.wmax:
                        return False
                    ## check if the new range will violates rmin 
                    if self.check_rest(task) != True: 
                        return False                     
#                     print('nothing was assigned on that day')
#                     print('CAN ASSIGN !')
                    return True

        ### otherwise check that req slot is not taken up >> cannot do two tasks at the same time
                elif task.hour not in [x.hour for x in self.tasks_assigned if x.day == task.day]:
#                     print('something assigned, but slots available')
#                     print('current hours taken:', [x.hour for x in self.tasks_assigned if x.day == task.day])

                    #### if the task fits within the existing range, if so, we can just assign.  
                    if task.hour >= self.blocks[task.day][0] and task.hour <= self.blocks[task.day][1]: 
#                         print('inside range')
#                         print('CAN ASSIGN !')
                        return True 

                    #### if required hour is outside range, then we have to do a few things below:  
                    else: 
#                         print('outside range')
                        ## calculate the new hours for evaluation  
                        new_block = self.calc_new_block(task)
                        old_block_hours = self.blocks[task.day][1] - self.blocks[task.day][0] + 1
                        new_block_hours = new_block[1] - new_block[0] + 1
                        new_weekly_hours = self.total_hours - old_block_hours + new_block_hours
                        ## check if new hours is within bmax or wmax  
                        if new_block_hours > self.bmax or new_weekly_hours > self.wmax:
#                             print('violate hours')
                            return False
                        ## check if the new range violates rest min (rmin)
                        if self.check_rest(task) != True: 
#                             print('violate rest')
                            return False 
                        
#                         print('CAN ASSIGN !')
                        # everything checks out fine, we can return true 
                        return True
                          
#         print('NOT POSSIBLE TO ASSIGN')
        # return false since the first condition has already failed 
        return False
    
    def assign_task(self, task):
        # first, check if nothing assigned on that day 
        if len([x.hour for x in self.tasks_assigned if x.day == task.day]) == 0: 
            # assign 
            self.tasks_assigned.append(task) 
            # update block [task]
            self.blocks[task.day] = [task.hour,task.hour]
            # to update total hour, just add 1 will do 
            self.total_hours += 1
        # if something assigned on the day already + no clash 
        else:
            # if the task fits within the existing range
            if task.hour >= self.blocks[task.day][0] and task.hour <= self.blocks[task.day][1]:
                # just assign only 
                self.tasks_assigned.append(task) 
            # outside range 
            else:
                # assign
                self.tasks_assigned.append(task)
                # update block 
                new_block = self.calc_new_block(task)
                self.blocks[task.day] = new_block
                # update total hour 
                self.total_hours = self.calc_task_hours()
                
    def remove_task(self, task_id):
        # identify the day and index  
        for x in range(len(self.tasks_assigned)):
            if self.tasks_assigned[x].id == task_id: 
                day = self.tasks_assigned[x].day
                index = x 
                break
        # if last task remaining for the day
        if len([x.hour for x in self.tasks_assigned if x.day == day]) == 1:
            # remove task
            self.tasks_assigned.pop(index)
            # remove the block 
            self.blocks.pop(day)
            # minus 1 hour 
            self.total_hours -= 1
        # not last task of the day ([within / outside] of range)
        else: 
            # remove task 
            self.tasks_assigned.pop(index)
            # update the block 
            remaining_hrs = [x.hour for x in self.tasks_assigned if x.day == day]
            self.blocks[day] = [min(remaining_hrs), max(remaining_hrs)]
            # update the hours 
            self.total_hours = self.calc_task_hours()
    
    # helper function to help me calculate the new block 
    def calc_new_block(self, task):
        # when there is an existing block 
        if task.day in self.blocks.keys():
            current_block = copy.deepcopy(self.blocks[task.day])
            current_block.append(task.hour)
            new_block = [min(current_block), max(current_block)]
        # when there is no existing block 
        else:
            new_block = [task.hour, task.hour]
        return new_block
    
    # helper function to help me check if the rest time violation has occured 
    def check_rest(self, task):
        # get the hypothetical new block of time for that day 
        new_block = self.calc_new_block(task)
        # check rest time to next block, if it exists 
        if (task.day+1) in self.blocks.keys():
            rest_time = (23 - new_block[1]) + self.blocks[task.day+1][0]
            if rest_time < self.rmin:
#                 print('violates next block')
                return False 
        # check rest time to the block before, if it exists  
        if (task.day-1) in self.blocks.keys():
            rest_time = (23 - self.blocks[task.day-1][1]) + new_block[0]
            if rest_time < self.rmin:
#                 print('violates previous block')
                return False 
        # everything checks out 
        return True 
    
    # work hours: sum of all blocks 
    # paid hours: sum of all blocks, minimum block length as 4 
    
    # calculates only the actual working hours of the worker a.k.a sum of all blocks
    def calc_task_hours(self):
        hours = sum([(x[1]-x[0]+1) for x in self.blocks.values()])
        return hours 
    
    # show data about the worker with : repr(m_d.workers[0])
    # def __str__(self):
    def __repr__(self):
        if len(self.blocks) == 0:
            return ''
        return '\n'.join([f'Worker {self.id}: Day {d} Hours {self.blocks[d]} Tasks {sorted([t.id for t in self.tasks_assigned if t.day == d])}' for d in sorted(self.blocks.keys())])
    
    # calculates the hours that need to be paid 
    def get_objective(self):
        t = sum(max(x[1]-x[0]+1,self.bmin) for x in self.blocks.values())
        # return self.total_hours * self.rate
        return t * self.rate
        
        
### GSP state class ###
# GSP state class. You could and should add your own helper functions to the class
# But please keep the rest untouched!
class GSP(State):
    
    def __init__(self, name, workers, tasks, alpha):
        '''Initialize the GSP state
        Args:
            name::str
                name of the instance
            workers::[Worker]
                workers of the instance
            tasks::[Task]
                tasks of the instance
        '''
        self.name = name
        self.workers = workers
        self.tasks = tasks 
        self.Alpha = alpha
        # the tasks assigned to each worker, eg. [worker1.tasks_assigned, worker2.tasks_assigned, ..., workerN.tasks_assigned]
        self.solution = []
        self.unassigned = list(tasks)


    def random_initialize(self, seed=None):
        '''
        Args:
            seed::int
                random seed
        Returns:
            objective::float
                objective value of the state
        '''
        if seed is None:
            seed = 606
        random.seed(seed)
        
        # sort the workers by the rates, lowest first 
        self.workers = sorted(self.workers, key=lambda x: x.rate)
        
        # deepcopy the current un assigned task 
        task_list = copy.deepcopy(self.unassigned)
        
        # randomise the copied task list 
        random.shuffle(task_list)
        
        # empty the self.unassigned 
        self.unassigned = []
        
        # while copied list is not empty: 
        while len(task_list) != 0: 

            current_task = task_list.pop(0)
            # for every worker available
            for idx in range(len(self.workers)): 
                # try to assign 
                result = self.workers[idx].can_assign(current_task)
                # if possible to assign
                if result == True: 
                    # assign 
                    self.workers[idx].assign_task(current_task)
                    # exit the for loop 
                    break
                    
            # no match was found, append to the unassigned list       
            if result == False:
                self.unassigned.append(current_task)
            
        # sort the worker by ID once more 
        self.workers = sorted(self.workers, key=lambda x: x.id)
        print('COMPLETE')
    
    def copy(self):
        return copy.deepcopy(self)
       
    
    def objective(self):
        ''' Calculate the objective value of the state
        Return the total cost of each worker + unassigned cost
        '''
        f1 = len(self.unassigned)
        f2 = sum(worker.get_objective() for worker in self.workers)
        return self.Alpha * f1 + f2