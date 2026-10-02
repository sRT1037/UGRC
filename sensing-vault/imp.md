
based on type of activity we can use windowing at diff .
have frequency bins along with time basd raw CSI

spectrogram = NOT time replaced by frequency, it's BOTH kept:
- what actually happens: for every time step n (still there, still in order), attach a vector of N_F frequency-bin values for that instant
- shape goes 1D (N_s time steps, 1 number each) -> 2D (N_F freq bins x N_s time steps) = the spectrogram
- time = still horizontal axis; frequency = new vertical axis added at each point, not a replacement
- so: not "instead of time, use frequency" -- "at every point in time, also tell me its frequency makeup." lose nothing about when, gain a cleaner what 

TCN , LSTM , GRU is used inorder to make use of spatiall data matching in the model itself rather than just time independednt data input classification.