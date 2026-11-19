$fn = 80;
part = "base";
pitch = 21;
base_height = 57;
socket_depth = 5.5;
peg_radius = 4.8;
cup_radius = 5.75;

module rounded_plate(length, width, height, radius) {
    hull() {
        for (x = [-1, 1], y = [-1, 1]) {
            translate([x*(length/2-radius), y*(width/2-radius), 0])
                cylinder(r=radius, h=height);
        }
    }
}

module base() {
    difference() {
        union() {
            rounded_plate(200, 50, 6, 5);
            hull() {
                translate([0,0,5.99]) rounded_plate(200, 50, .01, 5);
                translate([0,0,9]) rounded_plate(194, 44, .01, 4);
            }
            translate([0,0,9]) rounded_plate(194, 44, 48, 4);
        }
        for (i = [-4:4]) {
            translate([i*pitch, 0, base_height-socket_depth])
                cylinder(r=5.02, h=socket_depth+.02);
            translate([i*pitch, 0, base_height-.45])
                cylinder(r1=5.02, r2=5.47, h=.47);
        }
    }
}

module holder(visible_height) {
    top = 5.2 + visible_height;
    // Revolve one continuous section around the stem axis.
    rotate_extrude()
        polygon([
            [0,0], [4.35,0], [peg_radius,.45], [peg_radius,5.2],
            [8,8.4], [8,9.6], [6.4,11.2],
            [6.4,top-13], [8.5,top-10.9], [8.5,top-.8],
            [7.7,top], [6.35,top], [cup_radius,top-.6],
            [cup_radius,top-8], [0,top-8]
        ]);
}

if (part == "base") base();
if (part == "holder") holder(30);
if (part == "shamash") holder(53);

module emblem_back() {
    rounded_plate(46, 51, 1.8, 3);
}

module emblem_ink() {
    linear_extrude(.8) import("crest-red.svg", center=true);
}

if (part == "emblem-white") emblem_back();
if (part == "emblem-red") emblem_ink();
if (part == "emblem") {
    union() {
        emblem_back();
        translate([0,0,1.77]) linear_extrude(.83)
            import("crest-red.svg", center=true);
    }
}
