% Put a hologram from MATLAB on an SLM through the slmscreen Python package.
% Needs MATLAB R2022a or newer and a Python with `pip install slm-dmd-linux`.
pyenv(Version="/usr/bin/python3");
out = py.slmscreen.find_output(pyargs('edid_name', 'HE PLUTO-2.1'));    % `slmscreen list` prints the names
w = double(out.width); h = double(out.height);
[X, Y] = meshgrid(1:w, 1:h);
holo = uint8(mod(X * 16 + Y * 4, 256));                                  % a blazed grating; use your own here
slm = py.slmscreen.Display('slm', out);
info = slm.show(py.numpy.array(holo));
fprintf('on the panel at t_flip = %.6f\n', double(info{'t_flip'}));
pause(5);
slm.close();
