from enum import Enum
import random
from collections import deque
import numpy as np
from scipy.signal import convolve2d
from scipy.ndimage.filters import minimum_filter, maximum_filter




def dilation(arr, ksize=3):                

    ret_arr = np.copy(arr)
    dilation_kernel = np.ones((ksize, ksize))
    if ksize % 2 == 0: 
        l = int(ksize / 2.0)
        r = int(ksize / 2.0)
    else:
        l = int(np.floor(ksize / 2.0))
        r = int(np.floor(ksize / 2.0))+1    
            
    for iy in range(l, arr.shape[0]-r):
        for ix in range(l, arr.shape[1]-r):
            if np.any(arr[iy, ix]==0):
                ret_arr[iy-l:iy+r, ix-l:ix+r] = 0                            
    return ret_arr

class City:
    def __init__(self, w, h, debug=False):
        super().__init__()
        """
        self.dataが地図
        0: 走行可能
        1: 走行不可
        [2,...]:目的地番号, 偶数は排土場、奇数は積み込み場
        -1: ゴール
        -2: スタート

        目的地番号にしたがって車はそこを目指し続ける        
        
        """
        self.w = w
        self.h = h
        self.data = np.zeros((h, w), np.int)
        self.room = np.zeros((h, w), dtype=bool)
        self.corrider = np.zeros((h, w), dtype=bool)
        self.occupancuy = np.zeros((h, w), dtype=bool) # True = キャラがいる
        self.entrances = []
            
        self.location_idxs = list(range(2, 100))
        self.locations = {}
        self.dumpings = {} # 排土場所
        self.loadings = {} # 積み込み場所
        # {
        #      2: (x, y)
        # }
    
        self.goal_x = None
        self.goal_y = None
        self.start_x = None 
        self.start_y = None
        
        
        self.debug = debug         
        
    def create_map_stick_down(self):
        
        # 柱の設置
        for i in range(1, self.w)[::2]:
            for j in range(1, self.h)[::2]:
                self.data[j, i] = 1 # occupied
                
        # 柱を倒す
        for i in range(1, self.w)[::2]:
            for j in range(1, self.h)[::2]:
                num = np.random.randint(3) # [r,u,l,d] = [0, 1, 2, 3]
                if num == 0:
                    self.data[j, i+1] = 1
                elif num == 1:
                    self.data[j-1, i] = 1
                elif num ==2:
                    self.data[j, i-1] = 1
                elif num==3:
                    self.data[j+1, i] = 1
                    
    def create_map_digging(self):
        
        # 周囲を1つ大きくして通路、それ以外を壁とする
        self.data = np.zeros((self.h, self.w), dtype=np.int) # 通路        
        self.data[1:-1, 1:-1] = 1

        # 壁の中からx、yともに奇数の開始点を選ぶ
        idx = list(zip(*np.where(self.data==1)))
        xy = random.sample(idx, 1)[0]
        while True:
            xy = random.sample(idx, 1)[0]
            if xy[0]%2==1 and xy[1]%2==1:
                if 2 < xy[0] < self.data.shape[0]-2 and 2 < xy[1] < self.data.shape[1]-2:
                    break

        # 掘ったセルの記憶, だたしx, yともに奇数のもののみ格納
        digged = deque()
        digged.append(xy)
            
        # 開始点を通路にする
        self.data[xy[0], xy[1]] = 0
                
        # 掘り進める
        # l, d, r, u
        d = [(0,-1), (1,0), (0,1), (-1,0)]
        idx = [0, 1, 2, 3]
        while len(digged):
            rand_idx = random.sample(idx, 4)
            dig_OK = False
            for ridx in rand_idx:
                
                ny = xy[0] + d[ridx][0]
                nx = xy[1] + d[ridx][1]
                nny = xy[0] + 2*d[ridx][0]
                nnx = xy[1] + 2*d[ridx][1]
                                    
                # 掘っていいか判定する
                # 次が壁、次の次が道なら掘れない
                if self.data[ny, nx] == 1 and self.data[nny, nnx] == 1:
                    # 掘れそうなので掘る
                    self.data[ny, nx] = 0
                    self.data[nny, nnx] = 0

                    # 掘ったリストに記憶
                    digged.append((nny, nnx))
                    
                    # 次は掘った場所からスタート
                    xy = (nny, nnx)
                    dig_OK = True
                    break
                else:
                    # 掘れそににない
                    pass

            if not dig_OK:
                # 掘れなかったので、開始点を過去に掘った場所から探す
                xy = digged.popleft()
            
        self.data[0, :] = 1
        self.data[:, 0] = 1
        self.data[-1, :] = 1
        self.data[:, -1] = 1
                    
    def create_map_dungeon(self, num_col_rooms=3, 
                           num_row_rooms=2, 
                           corrider_width=1, 
                           min_room_size_ratio=0.3, 
                           max_room_size_ratio=0.8
                           ):
        """
        """

        self.data = np.ones(self.data.shape, np.int)
        
        # 適当に配列を分割する
        # NOTE: 各値は偶数でないと道がつながらない。
        rand_col_idx = [ int(e)&~1 for e in np.linspace(0, self.w-1, num=int(num_col_rooms)+1)]
        rand_row_idx = [ int(e)&~1 for e in np.linspace(0, self.h-1, num=int(num_row_rooms)+1)]

        # 各部屋の中心, 大きさ
        num_col_rooms = len(rand_col_idx) - 1
        num_row_rooms = len(rand_row_idx) - 1
        room_max_size_x = np.zeros((num_row_rooms, num_col_rooms),np.int)
        room_max_size_y = np.zeros((num_row_rooms, num_col_rooms),np.int)
        room_center_x = np.zeros((num_row_rooms, num_col_rooms),np.int)
        room_center_y = np.zeros((num_row_rooms, num_col_rooms),np.int)

        for ic in range(len(rand_col_idx)-1):
            for ir in range(len(rand_row_idx)-1):
                x = int(0.5 * (rand_col_idx[ic] + rand_col_idx[ic+1]))
                size_x = rand_col_idx[ic+1] - rand_col_idx[ic]
                y = int(0.5 * (rand_row_idx[ir] + rand_row_idx[ir+1]))
                size_y = rand_row_idx[ir+1] - rand_row_idx[ir]

                room_center_y[ir, ic] = int(y)
                room_max_size_y[ir, ic] = int(size_y)
                room_center_x[ir, ic] = int(x)
                room_max_size_x[ir, ic] = int(size_x)
        
        # 各部屋の大きさを決める
        room_size_x = np.zeros((num_row_rooms, num_col_rooms))
        room_size_y = np.zeros((num_row_rooms, num_col_rooms))
        for iy in range(num_row_rooms):
            for ix in range(num_col_rooms):            
                rmsx = room_max_size_x[iy,ix]
                rmsy = room_max_size_y[iy,ix]
                
                rsx = np.random.randint(int(rmsx * min_room_size_ratio), int(rmsx * max_room_size_ratio))
                rsy = np.random.randint(int(rmsy * min_room_size_ratio), int(rmsy * max_room_size_ratio))
                room_size_x[iy, ix] = rsx
                room_size_y[iy, ix] = rsy
    
        # 各部屋を塗りつぶす + 通路をつくる
        corriders = np.ones(self.data.shape, np.int)
        self.entrances = []
        for iy in range(num_row_rooms):
            for ix in range(num_col_rooms):            
                w = room_size_x[iy, ix]
                h = room_size_y[iy, ix]
                cx = room_center_x[iy, ix]
                cy = room_center_y[iy, ix]                
                rmsx = room_max_size_x[iy,ix]
                rmsy = room_max_size_y[iy,ix]
                self.data[cy-int(h/2.0):cy+int(h/2.0), cx-int(w/2.0):cx+int(w/2.0)] = 0
                self.room[cy-int(h/2.0):cy+int(h/2.0), cx-int(w/2.0):cx+int(w/2.0)] = True
        
                # 各部かから通路への垂線を上下左右４本分生成
                exit_x_up = np.random.randint(cx-int(w/2.0)+1, cx+int(w/2.0)-1)
                exit_x_down = np.random.randint(cx-int(w/2.0)+1, cx+int(w/2.0)-1)
                exit_left = np.random.randint(cy-int(h/2.0)+1, cy+int(h/2.0)-1)
                exit_right = np.random.randint(cy-int(h/2.0)+1, cy+int(h/2.0)-1)
                
                # cxからcx+rmsx/2.0, cx-rmsx/2.0だけ線を引く
                # ただし, 端に触れていへ部屋は通路をつくらない
                
                rx = int(rmsx/2.0)
                ry = int(rmsy/2.0)
                rsx = int(room_size_x[iy, ix]/2.0)
                rsy = int(room_size_y[iy, ix]/2.0)
                
                # 列が1つの場合
                if num_row_rooms == 1 and ix == 0:
                    corriders[exit_right, cx:cx+rx] = 0
                    self.entrances.append((exit_right-1, cx+rsx))
                    
                elif num_row_rooms == 1 and ix == num_col_rooms-1:
                    corriders[exit_left, cx-rx:cx] = 0
                    self.entrances.append((exit_left+1, cx-rsx))
                    
                # 行が1つの場合
                elif num_col_rooms == 1 and iy == 0:
                    corriders[cy:cy+ry, exit_x_down] = 0
                    self.entrances.append((cy+rsy, exit_x_down+1))
                    
                elif num_col_rooms == 1 and iy == num_row_rooms-1:
                    corriders[cy-ry:cy, exit_x_up] = 0
                    self.entrances.append((cy-rsy, exit_x_up-1))

                elif iy == 0 and ix == 0:
                    corriders[exit_right, cx:cx+rx] = 0
                    corriders[cy:cy+ry, exit_x_down] = 0
                    self.entrances.append((exit_right-1, cx+rsx))
                    self.entrances.append((cy+rsy, exit_x_down+1))
                # 
                elif iy == num_row_rooms-1 and ix == num_col_rooms-1:
                    corriders[exit_left, cx-rx:cx] = 0
                    corriders[cy-ry:cy, exit_x_up] = 0
                    self.entrances.append((exit_left+1, cx-rsx))
                    self.entrances.append((cy-rsy, exit_x_up-1))
                # 
                elif iy == 0 and ix == num_col_rooms-1:
                    corriders[exit_left, cx-rx:cx] = 0
                    corriders[cy:cy+ry, exit_x_down] = 0
                    self.entrances.append((exit_left+1, cx-rsx))
                    self.entrances.append((cy+rsy, exit_x_down+1))
                # 
                elif iy == num_row_rooms-1 and ix == 0:
                    corriders[exit_right, cx:cx+rx] = 0
                    corriders[cy-ry:cy, exit_x_up] = 0
                    self.entrances.append((exit_right-1, cx+rsx))
                    self.entrances.append((cy-rsy, exit_x_up-1))
                # 
                elif iy == num_row_rooms-1 and ix == 0:
                    corriders[exit_right, cx:cx+rx] = 0
                    corriders[cy-ry:cy, exit_x_up] = 0
                    self.entrances.append((exit_right-1, cx+rsx))
                    self.entrances.append((cy-rsy, exit_x_up-1))

                elif iy == 0:
                    corriders[exit_left, cx-rx:cx] = 0
                    corriders[exit_right, cx:cx+rx] = 0
                    corriders[cy:cy+ry, exit_x_down] = 0
                    self.entrances.append((exit_right-1, cx+rsx))
                    self.entrances.append((exit_left+1, cx-rsx))
                    self.entrances.append((cy+rsy, exit_x_down+1))
                #   

                elif iy == num_row_rooms-1:
                    corriders[exit_left, cx-rx:cx] = 0
                    corriders[exit_right, cx:cx+rx] = 0
                    corriders[cy-ry:cy, exit_x_up] = 0
                    self.entrances.append((exit_right-1, cx+rsx))
                    self.entrances.append((exit_left+1, cx-rsx))                    
                    self.entrances.append((cy-rsy, exit_x_up-1))

                elif ix == 0:
                    corriders[exit_right, cx:cx+rx] = 0
                    corriders[cy-ry:cy, exit_x_up] = 0
                    corriders[cy:cy+ry, exit_x_down] = 0
                    self.entrances.append((exit_right-1, cx+rsx))
                    self.entrances.append((cy+rsy, exit_x_down+1))
                    self.entrances.append((cy-rsy, exit_x_up-1))

                elif ix == num_col_rooms-1:
                    corriders[exit_left, cx-rx:cx] = 0
                    corriders[cy-ry:cy, exit_x_up] = 0
                    corriders[cy:cy+ry, exit_x_down] = 0
                    self.entrances.append((exit_left+1, cx-rsx))                    
                    self.entrances.append((cy+rsy, exit_x_down+1))
                    self.entrances.append((cy-rsy, exit_x_up-1))
                            
                else:                
                    corriders[exit_left, cx-rx:cx] = 0
                    corriders[exit_right, cx:cx+rx] = 0
                    corriders[cy-ry:cy, exit_x_up] = 0
                    corriders[cy:cy+ry, exit_x_down] = 0
                    self.entrances.append((exit_right-1, cx+rsx))
                    self.entrances.append((exit_left+1, cx-rsx))                    
                    self.entrances.append((cy+rsy, exit_x_down+1))
                    self.entrances.append((cy-rsy, exit_x_up-1))
                    
        # エントランスには通かから入れないようにする
        # 通路のセルとエントランスに特別す数字をふって、
        # 通路-->エントランスだとコスト無限大とする
        # print(self.entrances)

        # 線をつなげる
        rand_col_idx = np.array(rand_col_idx)
        for col_idx in rand_col_idx[1:-1]:
            end_y_l = np.where(corriders[:, col_idx - 1]== 0 )
            end_y_r = np.where(corriders[:, col_idx + 1]== 0 )
            for idx in range(num_row_rooms):
                end_y = sorted([end_y_l[0][idx], end_y_r[0][idx]])
                corriders[end_y[0]:end_y[1]+1, col_idx] = 0                

        rand_row_idx = np.array(rand_row_idx)
        for row_idx in rand_row_idx[1:-1]:
            end_x_u = np.where(corriders[row_idx - 1, :]== 0 )
            end_x_d = np.where(corriders[row_idx + 1, :]== 0 )
            for idx in range(num_col_rooms):
                end_x = sorted([end_x_u[0][idx], end_x_d[0][idx]])
                corriders[row_idx, end_x[0]:end_x[1]+1] = 0                

        if corrider_width > 1:            
            dilated_corriders = dilation(corriders, ksize=corrider_width)            
            corriders = np.logical_xor(dilated_corriders.astype(np.bool), ~(corriders).astype(np.bool))
            # TODO: corridersに特別な値いいれる
            
            
        self.data = np.logical_and(self.data, corriders)


        # 各部屋に場所番号を与える
        idx = 0
        for iy in range(len(rand_row_idx)-1):
            for ix in range(len(rand_col_idx)-1):

                cx = room_center_x[iy, ix]
                cy = room_center_y[iy, ix]                
                
                # self.data[cy, cx] = self.location_idxs[idx % len(self.location_idxs)]
                # print(cx, cy, self.data[cy, cx])
                self.locations[self.data[cy, cx]] = (cy, cx)
                idx += 1
            
        # 積み込み場と排土場に分ける TODO:偶奇でわけているだけ
        self.dumpings = {e[0]:e[1] for e in self.locations.items() if e[0] % 2 == 0}
        self.loadings = {e[0]:e[1] for e in self.locations.items() if e[0] % 2 != 0}

    def get_free_space(self, num=1):
        
        idx = list(zip(*np.where(self.data==0)))
        xy = random.sample(idx, num)
        # x = random.sample(range(self.w), num, replace=False)
        # y = random.choice(range(self.h), num, replace=False)
        # x = np.random.randint(self.w)
        # y = np.random.randint(self.h)        
        # while self.data[y, x] != 0:
        #     x = random.choice(range(self.w), num, replace=False)
        #     y = random.choice(range(self.h), num, replace=False)

        #     x = np.random.randint(self.w)
        #     y = np.random.randint(self.h)        
    
        return xy

    def set_start(self):

        # 地図中にスタートがあれば通路0に置き換え
        self.data = np.where(self.data == -2, 0, self.data)
        
        # 通路0を引くまでランダムに選択する TODO: np.where + random.sampleで置き換える
        x = np.random.randint(self.w)
        y = np.random.randint(self.h)        
        while self.data[y, x] != 0 and self.data[y, x] != -1:
            x = np.random.randint(self.w)
            y = np.random.randint(self.h)        

        # self.data[y, x] = -2 # Start書き込まない
        self.start_x = x
        self.start_y = y
        
    def set_goal(self):
        # 地図中にゴールがあれば通路0に置き換えTODO: np.where + random.sampleで置き換える
        self.data = np.where(self.data == -1, 0, self.data)

        x = np.random.randint(self.w)
        y = np.random.randint(self.h)        
        while self.data[y, x] != 0 and self.data[y, x] != -2:
            x = np.random.randint(self.w)
            y = np.random.randint(self.h)        

        self.data[y, x] = -1 # Goal
        self.goal_x = x
        self.goal_y = y
 
    def search_shortest_path_dws(self, start, goal):
        """
        start = (y, x)
        goal = (y, x)
        """
        import matplotlib.pyplot as plt
        import matplotlib.cm as cm
        import matplotlib.colors as colors
        import numpy as np
        cmap = cm.jet
        cmap_data = cmap(np.arange(cmap.N))
        cmap_data[0, 3] = 0 # 0 のときのα値を0(透明)にする
        customized_jet = colors.ListedColormap(cmap_data)

        cmap = cm.cool
        cmap_data = cmap(np.arange(cmap.N))
        cmap_data[0, 3] = 0 # 0 のときのα値を0(透明)にする
        customized_cool = colors.ListedColormap(cmap_data)

        cmap = cm.gist_yarg
        cmap_data = cmap(np.arange(cmap.N))
        cmap_data[0, 3] = 0 # 0 のときのα値を0(透明)にする
        customized_gist_yarg = colors.ListedColormap(cmap_data)

        
        start_goal = np.zeros((self.h, self.w), dtype=int)
        cost = np.zeros((self.h, self.w), dtype=int) + 1E10
        done = np.zeros((self.h, self.w), dtype=bool)
        barrier = np.zeros((self.h, self.w), dtype=bool) # occupancyも含める
        path = np.zeros((self.h, self.w), dtype=int)
        entrance = np.zeros((self.h, self.w), dtype=bool)
        
        #プーリング用のフィルタ
        g = np.array([[0, 1, 0],
                      [1, 1, 1],
                      [0, 1, 0]])
        
        for iy in range(self.h):
            for ix in range(self.w):
                if iy == start[0] and ix == start[1]:
                    cost[iy, ix] = 0
                    done[iy, ix] = True
                    start_goal[iy, ix] = -255
                if iy == goal[0] and ix == goal[1]:                
                    start_goal[iy, ix] = 255
                if self.data[iy, ix] == 1: # barrier
                    barrier[iy, ix] = True 
                if (iy, ix) in self.entrances:
                    entrance[iy, ix] = True                

        barrier = barrier + self.occupancuy
        barrier[start[0], start[1]] = False
        barrier[goal[0], goal[1]] = False
    
        plt.imshow(barrier, cmap="gist_yarg")
        plt.imshow(entrance, cmap=customized_cool)
        plt.show()
        
        # print('start\n{}'.format(start))
        # print('goal\n{}'.format(goal))
        # print('cost\n{}'.format(cost))
        # print('done\n{}'.format(done))
        # print('barrier\n{}'.format(barrier))
 
        for i in range(1, 10000000):

            #次に進出するマスのbool
            done_next = maximum_filter(done, footprint=g) * ~done
            
            # ExitにはRoomからは入れない、という処理をしたい
            # done_nextがentranceを踏んだとき、隣接するdoneをチェッしして
            # 逆順になっていればbarrierと同様にふるまう
            is_entrance = done_next * entrance
            # plt.imshow(barrier, cmap=customized_gist_yarg)
            # plt.imshow(is_entrance, cmap=customized_cool)
            # plt.show()
            
            
            
            # print('done_next\n{}'.format(done_next))
            # plt.imshow(barrier, cmap=customized_gist_yarg)
            # plt.imshow(done, cmap=customized_cool, alpha=0.5)
            # plt.show()

            #次に進出するマスのcost
            cost_next = minimum_filter(cost, footprint=g) * done_next
            cost_next[done_next] += 1   
    
            # is_entranceがTrueのそれぞれのセルについて、
            entrance_xy = list(zip(*np.where(is_entrance == True)))
            for ey, ex in entrance_xy:
                
                if done[ey-1, ex] == True and self.room[ey-1, ex] != True:
                    cost_next[ey, ex] = 10000000
                    done_next[ey, ex] = False
                    print(f"This is entrance, {ey}, {ex}")

                if done[ey, ex+1] == True and self.room[ey, ex+1] != True:
                    cost_next[ey, ex] = 10000000
                    done_next[ey, ex] = False
                    print(f"This is entrance, {ey}, {ex}")

                if done[ey+1, ex] == True and self.room[ey+1, ex] != True:
                    cost_next[ey, ex] = 10000000
                    done_next[ey, ex] = False
                    print(f"This is entrance, {ey}, {ex}")

                if done[ey, ex-1] == True and self.room[ey, ex-1] != True:
                    cost_next[ey, ex] = 10000000
                    done_next[ey, ex] = False
                    print(f"This is entrance, {ey}, {ex}")


            #print('cost_next\n{}'.format(cost_next))
            # plt.imshow(barrier, cmap=customized_gist_yarg)
            # plt.imshow(cost, cmap=customized_jet, vmax=100, vmin=0, alpha=0.5)
            # plt.show()
            
            #costを更新
            cost[done_next] = cost_next[done_next]
            
            #ただし障害物のコストは10000000とする
            cost[barrier] = 10000000
            #print('cost\n{}'.format(cost))
            
            #探索終了マスを更新
            done[done_next] = done_next[done_next]
            
            #ただし障害物は探索終了としない
            done[barrier] = False
            #print('done\n{}'.format(done))
            
            # x, y = np.where(cost != 10000000)
            # c = cost[x, y]
            # for i in range(len(x)):
                # plt.text(y[i]-0.1, x[i]+0.1, c[i], size = 20, color = 'gray')

            
            #終了判定
            if done[goal[0], goal[1]] == True:
                break
                    #表示

            
        plt.imshow(cost, cmap=customized_jet, vmax=1000, vmin=0, alpha=1)
        barrier[goal[0], goal[1]] = 255
        barrier[start[0], start[1]] = 255
        plt.imshow(barrier, cmap=customized_gist_yarg)
        plt.show()


        point_now = goal
        cost_now = cost[goal[0], goal[1]]
        route = [goal]
        # print('route\n{}'.format(route))
        
        while cost_now > 0:
            
            #上から来た場合
            try:
                if cost[point_now[0] - 1, point_now[1]] == cost_now - 1:
                    #更新
                    point_now = (point_now[0] - 1, point_now[1])
                    cost_now = cost_now - 1
                    #記録
                    route.append(point_now)
            except: pass
            #下から来た場合
            try:
                if cost[point_now[0] + 1, point_now[1]] == cost_now - 1:
                    #更新
                    point_now = (point_now[0] + 1, point_now[1])
                    cost_now = cost_now - 1
                    #記録
                    route.append(point_now)
            except: pass
            #左から来た場合    
            try:
                if cost[point_now[0], point_now[1] - 1] == cost_now - 1:
                    #更新
                    point_now = (point_now[0], point_now[1] - 1)
                    cost_now = cost_now - 1
                    #記録
                    route.append(point_now)
            except: pass
            #右から来た場合
            try:
                if cost[point_now[0], point_now[1] + 1] == cost_now - 1:
                    #更新
                    point_now = (point_now[0], point_now[1] + 1)
                    cost_now = cost_now - 1
                    #記録
                    route.append(point_now)
            except: pass

        #ルートを逆順にする
        route = route[::-1]
                
        for cell in route:
            ix = cell[1]
            iy = cell[0]
            path[iy, ix] = 1

        if self.debug:        
            plt.imshow(path, cmap=customized_cool)        
            plt.imshow(barrier, cmap=customized_gist_yarg)
            plt.show()
        return route
    
    # def solve_dws(self, maze, y, x):
    #     if maze[y, x] == -1: # GOAL
    #         return [(y, x)]
    #     maze[y, x] = 1
    #     for (n_y, n_x) in [(y+1, x),(y, x+1),(y, x-1),(y-1, x)]:
    #         if maze[n_y, n_x] == 1:
    #             continue
    #         route = self.solve_dws(maze, n_y, n_x)
    #         if route:
    #             return [(y, x)] + route
        
    def solve(self, maze, y, x, checked):
        checked.append((y, x))
        # print(checked)
        if maze[y, x] == -1:
            return [(y, x)]
        for next_y, next_x in (y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1):
            if not  (0 <= next_y < maze.shape[0] and 0 <= next_x < maze.shape[1]): 
                continue
            if (next_y, next_x) in checked:
                continue
            if maze[next_y, next_x] == 1:
                continue
            route = self.solve(maze, next_y, next_x, checked)
            if route:
                return [(y, x)] + route
    
    def bfs(self, sy, sx, gy, gx):
        
        queue = deque()
        queue.append((sy, sx))
        distance = np.ones((self.h, self.w), dtype=np.int) * 1000000
        distance[sy, sx] = 0    
        route = deque()
        route.append((sy, sx))
        while len(queue):
            y, x = queue.pop()
            if x == gx and y == gy:
                break
            
            for i in range(0, 4):
                nx= x + [1, 0, -1, 0][i]
                ny= y + [0, 1, 0, -1][i]
        
                if 0 <= nx < self.w \
                    and 0 <= ny < self.h \
                    and self.data[ny, nx] != 1 \
                    and distance[ny, nx] == 1000000:
                    
                    queue.appendleft((ny, nx))
                    distance[ny, nx] = distance[y, x] +  1
                    route.append((ny, nx))
                    
        route.append((gy, gx))
        return distance[gy, gx], route
    
if __name__ == "__main__":

    from collections import deque
    
    width = 99
    height = 99
    map = City(width, height, debug=True)
    # map.create_map_stick_down()
    map.create_map_digging()
    # map.create_map_dungeon(num_col_rooms=8, num_row_rooms=8, corrider_width=1)
    map.set_goal()
    map.set_start()
    print((map.start_y, map.start_x), (map.goal_y, map.goal_x))
    route = map.search_shortest_path_dws((map.start_y, map.start_x), (map.goal_y, map.goal_x))
    route_deque = deque(route)
    print(route_deque)
    print(len(route_deque))
    
    # route = map.solve(map.data, map.start_y, map.start_x, checked=[])
    # # print(len(route))
    # path = np.zeros((map.h, map.w), dtype=np.int)    
    # for cell in route:
    #     ix = cell[1]
    #     iy = cell[0]
    #     path[iy, ix] = 1

    # import matplotlib.pyplot as plt
    # import matplotlib.cm as cm
    # import matplotlib.colors as colors
    # import numpy as np

    # cmap = cm.cool
    # cmap_data = cmap(np.arange(cmap.N))
    # cmap_data[0, 3] = 0 # 0 のときのα値を0(透明)にする
    # customized_cool = colors.ListedColormap(cmap_data)

    # cmap = cm.gist_yarg
    # cmap_data = cmap(np.arange(cmap.N))
    # cmap_data[0, 3] = 0 # 0 のときのα値を0(透明)にする
    # customized_gist_yarg = colors.ListedColormap(cmap_data)

    # plt.imshow(map.data, cmap=customized_gist_yarg)
    # plt.imshow(path, cmap=customized_cool)
    # plt.show()
    
    # print(map.bfs(map.start_y, map.start_x, map.goal_y, map.goal_x))